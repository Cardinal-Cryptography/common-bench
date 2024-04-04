import pickle
import random
from os.path import join
from substrateinterface import ContractInstance, Keypair, SubstrateInterface
from substrateinterface.exceptions import ContractReadFailedException

from .utils import check_file, check_url


class Dex:
    """Data structure for storing information about on-chain dex.

    Holds contract addresses of all available PSP22 tokens, as well as information about
    how they are connected with Pair contracts. Allows generating random trade path of a given length.

    Apart from fetch_info(), which interacts with the chain, this object is totally static and offline
    (dictionaries of strings). Can be safely juggled between different processes, copied, pickled etc.
    """

    def __init__(self, chain_url, router_address, metadata_dict, report=True):
        self.chain_url = chain_url
        self.router_address = router_address
        self.factory_address = None
        self.wnative_address = None
        self.router_metadata = metadata_dict['router']
        self.factory_metadata = metadata_dict['factory']
        self.pair_metadata = metadata_dict['pair']
        self.psp22_metadata = metadata_dict['psp22']
        self.report = report
        self.tokens = {}
        self.token_symbols = {}
        self.pairs = {}

    def log(self, msg):
        if self.report:
            print(msg, end='')

    def random_path(self, start, max_length=1):
        result = [start]
        while len(result) <= max_length:
            candidates = set(self.tokens[result[-1]]) - set(result)
            if len(candidates) == 0:
                break
            result.append(random.choice(list(candidates)))
        return result

    def get_pair(self, token_0, token_1):
        return self.pairs[(token_0, token_1)] if token_0 < token_1 else self.pairs[(token_1, token_0)]

    def fetch_info(self):
        """Call the chain and fetch the following info:
            a) factory address
            b) wnative address
            c) addresses of all pairs registered in the factory
            d) addresses all PSP22 tokens associated with these pairs
            e) if possible, also tokens symbols

        Store the dex structure in self.tokens dict, in a form of graph of psp22 token addresses.
        """

        kp = Keypair.create_from_uri('//Alice')  # dummy keypair for read methods
        chain = SubstrateInterface(url=check_url(self.chain_url))

        router = ContractInstance.create_from_address(self.router_address, self.router_metadata, chain)
        self.factory_address = router.read(kp, method='Router::factory').contract_result_data.value['Ok']
        self.log(f'Factory address: {self.factory_address}\n')
        self.wnative_address = router.read(kp, method='Router::wnative').contract_result_data.value['Ok']
        self.log(f'Wnative address: {self.wnative_address}\n')

        factory = ContractInstance.create_from_address(self.factory_address, self.factory_metadata, chain)
        n_pairs = factory.read(kp, method='Factory::all_pairs_length').contract_result_data.value['Ok']
        self.log(f'Found {n_pairs} trading pairs.\nFetching pair info...')

        for i in range(n_pairs):
            self.log(f' {i}')
            pair_address = factory.read(kp, method='Factory::all_pairs', args={'pid': i}).contract_result_data.value['Ok']
            pair = ContractInstance.create_from_address(pair_address, self.pair_metadata, chain)
            token_0 = pair.read(kp, method='Pair::get_token_0').contract_result_data.value['Ok']
            token_1 = pair.read(kp, method='Pair::get_token_1').contract_result_data.value['Ok']
            if token_0 not in self.tokens:
                self.tokens[token_0] = []
            self.tokens[token_0].append(token_1)
            if token_1 not in self.tokens:
                self.tokens[token_1] = []
            self.tokens[token_1].append(token_0)
            if token_0 < token_1:
                self.pairs[(token_0, token_1)] = pair_address
            else:
                self.pairs[(token_1, token_0)] = pair_address

        self.log('\nAll pairs processed. Fetching token symbols\n')
        for t in self.tokens:
            token = ContractInstance.create_from_address(t, self.psp22_metadata, chain)
            try:
                self.token_symbols[t] = token.read(kp, method='PSP22Metadata::token_symbol').contract_result_data.value['Ok']
            except ContractReadFailedException:
                self.token_symbols[t] = None

        self.log(f'Found {len(self.tokens)} tokens:\n')
        for addr, sym in self.token_symbols.items():
            self.log(f' {sym}\t  {addr}\n')

    def save_to_file(self, path='', filename=None):
        if filename is None:
            chain_id = self.chain_url.split('/')[-1]
            filename = f'{chain_id}.{self.router_address[:6]}.dex'
        path = join(path, filename)
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        self.log(f'Dex data saved to {path}')

    @classmethod
    def load_from_file(cls, filename):
        with open(check_file(filename), 'rb') as f:
            return pickle.load(f)
