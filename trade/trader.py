import random
from substrateinterface import Keypair, SubstrateInterface, ContractInstance
from substrateinterface.exceptions import ContractReadFailedException

from .utils import build_contract_call, call_contract, check_url, fee, weight, send_batch, send_single_call

FOREVER = 10**18
ALLOWANCE = 10**24
NATIVE = 'AZERO'


class Trader:
    """Class for sending trade transactions to the router of Common dex.

    Uses on-chain account associated with `phrase`. The account must be funded with some coins to cover fees.
    Extracts all needed information (chain URL, router address, token addresses) from supplied Dex instance.
    Keeps track of balances of all dex tokens. Trades along a random path of PSP22 contracts (connected by Pairs)
    of a given length. Uses only swap methods with exact input and and does not care about the slippage
    (will accept any positive amount of output tokens).

    Trades are performed via single router call, no batching with `approve` transactions. Because of that,
    dex token contracts must be approved beforehand (by calling set_allowances()).
    """
    def __init__(self, dex, phrase, report=True, change_port=None):
        self.kp = Keypair.create_from_uri(phrase)
        self.dex = dex
        url = check_url(dex.chain_url)
        if change_port:
            url = url.rsplit(':', 1)[0] + f':{change_port}'
        self.chain = SubstrateInterface(url=url)
        self.router = ContractInstance.create_from_address(dex.router_address, dex.router_metadata, self.chain)
        self.report = report
        self.balances = {NATIVE: 0}
        self.tokens = {}
        for t in dex.tokens:
            self.balances[t] = 0
            self.tokens[t] = ContractInstance.create_from_address(t, dex.psp22_metadata, self.chain)

    def log(self, msg):
        if self.report:
            print(msg, end='')

    def addr(self):
        return self.kp.ss58_address

    def symbol(self, addr):
        return self.dex.token_symbols[addr] if addr != self.dex.wnative_address else 'A_0'

    def update_balances(self, tokens=None):
        balance = self.chain.query('System', 'Account', [self.addr()]).value['data']['free']
        self.balances[NATIVE] = balance
        tokens = tokens or list(self.tokens.keys())
        for t in tokens:
            try:
                self.balances[t] = self.tokens[t].read(self.kp, method='PSP22::balance_of', args={'owner': self.addr()}).contract_result_data.value['Ok']
            except ContractReadFailedException:
                self.log(f'Fetching balance of {self.symbol(t)} FAILED\n')

    def show_balances(self):
        for t in self.balances:
            s = self.dex.token_symbols.get(t, NATIVE)
            self.log(f'{s}\t\t{self.balances[t]}\n')

    def set_allowances(self, value=ALLOWANCE, tokens=None):
        tokens = tokens or list(self.dex.tokens.keys())
        router = self.router.contract_address
        calls = []
        for t in tokens:
            if t != self.dex.wnative_address:
                call = build_contract_call(self.tokens[t], self.kp, method='PSP22::approve', args={'spender': router, 'value': value})
                calls.append(call)
        receipt = send_batch(calls, self.chain, self.kp)
        if not receipt.is_success:
            print(f'Error in batch transfer: {receipt.error_message["docs"]}')

    def trade(self, max_path_len=2, minimal_balance=1000000):
        candidates = [t for t in self.balances if self.balances[t] >= minimal_balance and t != self.dex.wnative_address]
        start = random.choice(candidates)
        if start == NATIVE:
            start = self.dex.wnative_address
        path = self.dex.random_path(start, max_path_len)
        if path[0] == self.dex.wnative_address:
            balance = self.balances[NATIVE]
            amount = random.randint(int(0.0001 * balance), int(0.01 * balance))
        else:
            balance = self.balances[path[0]]
            amount = random.randint(int(0.2 * balance), int(0.6 * balance))
        self.log(f'Trade {"->".join(list(map(self.symbol,path)))}  ')

        if path[0] == self.dex.wnative_address:
            receipt = self.trade_native_for_token(path, amount)
        else:
            receipt = self.trade_tokens(path, amount)

        if receipt.is_success:
            if self.report:
                block = receipt.get_extrinsic_identifier().split('-')[0]
                self.log(f'weight {weight(receipt):.1f}  fee {fee(receipt):.5f}  block {block}\n')
            self.update_balances([path[0], path[-1]])
        else:
            self.log('FAILED\n')
        return receipt

    def trade_native_for_token(self, path, amount):
        args = {'path': path, 'amount_out_min': 1, 'to': self.addr(), 'deadline': FOREVER}
        return call_contract(self.router, self.kp, method='Router::swap_exact_native_for_tokens', args=args, value=amount)

    def trade_tokens(self, path, amount):
        method = 'Router::swap_exact_tokens_for_native' if path[-1] == self.dex.wnative_address else 'Router::swap_exact_tokens_for_tokens'
        args = {'path': path, 'amount_in': amount, 'amount_out_min': 1, 'to': self.addr(), 'deadline': FOREVER}
        return call_contract(self.router, self.kp, method=method, args=args)

#    def trade_native_for_token(self, path, amount):
#        args = {'path': path, 'amount_out_min': 1, 'to': self.addr(), 'deadline': FOREVER}
#        call = build_contract_call(self.router, self.kp, method='Router::swap_exact_native_for_tokens', args=args, value=amount)
#        return send_single_call(call, self.chain, self.kp)
#
#    def trade_tokens(self, path, amount):
#        appr_args = {'spender': self.router.contract_address, 'delta_value': amount}
#        method = 'Router::swap_exact_tokens_for_native' if path[-1] == self.dex.wnative_address else 'Router::swap_exact_tokens_for_tokens'
#        trade_args = {'path': path, 'amount_in': amount, 'amount_out_min': 0, 'to': self.addr(), 'deadline': FOREVER}
#        approve = build_contract_call(self.tokens[path[0]], self.kp, method='PSP22::increase_allowance', args=appr_args)
#        trade = build_contract_call(self.router, self.kp, method=method, args=trade_args)
#        #return send_single_call(trade, self.chain, self.kp)
#        return send_batch([approve, trade], self.chain, self.kp)

    def trade_direct(self, minimal_balance=1000000):
        weight = 0
        candidates = [t for t in self.balances if self.balances[t] >= minimal_balance and t != self.dex.wnative_address and t != NATIVE]
        start = random.choice(candidates)
        path = self.dex.random_path(start, 1)
        balance = self.balances[path[0]]
        amount = random.randint(int(0.2 * balance), int(0.6 * balance))
        self.log(f'Direct trade {"->".join(list(map(self.symbol,path)))}  ')
        pair_address = self.dex.get_pair(path[0], path[1])
        token_in = ContractInstance.create_from_address(path[0], self.dex.psp22_metadata, self.chain)
        receipt = call_contract(token_in, self.kp, method='PSP22::transfer', args={'to': pair_address, 'value': amount, '_data': []})
        if not receipt.is_success:
            self.log('PSP22 transfer failed!\n')
            return
        weight_tr = weight(receipt)

        pair = ContractInstance.create_from_address(pair_address, self.dex.pair_metadata, self.chain)
        reserves = pair.read(keypair=self.kp, method='Pair::get_reserves').contract_result_data.value['Ok']
        if path[0] < path[1]:
            amount_0_out = 0
            amount_1_out = get_amount_out(amount, reserves[0], reserves[1])
        else:
            amount_0_out = get_amount_out(amount, reserves[1], reserves[0])
            amount_1_out = 0
        args = {'amount_0_out': amount_0_out, 'amount_1_out': amount_1_out, 'to': self.addr(), 'data': None}
        receipt = call_contract(pair, self.kp, method='Pair::swap', args=args)
        if receipt.is_success:
            weight = weight(receipt)
            self.log(f'weights {weight_tr} {weight} \n')
            self.update_balances([path[0], path[1]])
        else:
            self.log('FAILED\n')
        return receipt


def get_amount_out(amount_in, reserve_0, reserve_1):
    return (amount_in * 997 * reserve_1) // (reserve_0 * 1000 + amount_in * 997)
