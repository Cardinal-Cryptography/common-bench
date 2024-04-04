from multiprocessing import Event, Process, Queue, Value
from substrateinterface.exceptions import SubstrateRequestException
from websocket import WebSocketConnectionClosedException
from time import sleep, time

from .trader import Trader


class TraderPool:
    """Manager of a horde of traders.

    Each trader runs in a separate process and waits for a singal to perform a trade.
    Signals are passed using a common queue. The signal should be a positive int,
    indicating how many atomic swaps the trade should consist of (occasionally a trader may
    decide to use a shorter path if the value is too large and they have problems finding a
    random path with the given length).

    The supplied seed phrase is used as a base for traders' keypairs. Each of them will use that
    phrase with followed by a derivation path consisting of consecutive natural numbers (//0, //1, etc.)
    For that reason the supplied path SHOULD NOT have any derivation paths, just 12 words.

    NOTE! Please make sure that all the accounts {phrase}//0, {phrase}//1, ... {phrase}//(n-1) have some
    native coin available for trading and fees

    Usage pattern:
    t = TraderPool(...)

    # if True, each trader will send approve(10^24) tx for each PSP22 token present in the dex.
    # can be skipped when these accounts have been previously used in TraderPool
    t.spawn_traders(True)

    # schedule 100 trades with 2 swaps each. Traders will start sending tx immediately.
    t.order_trades(100, 2)

    # terminate trader processes. Each will print a statistics of all performed trades
    t.kill_traders()
    """
    def __init__(self, dex, n_traders, phrase):
        self.dex = dex
        self.n_traders = n_traders
        self.phrase = phrase
        self.queue = Queue()
        self.traffic_maker = None
        self.tps = Value('i', 0)

    def spawn_traders(self, set_allowance=True):
        events = [Event() for _ in range(self.n_traders)]
        proc = [Process(target=worker, args=(self.queue, events[i], self.dex, self.phrase, i, set_allowance)) for i in range(self.n_traders)]
        for p in proc:
            p.start()
        for e in events:
            e.wait()

    def order_trades(self, n, steps=1):
        for _ in range(n):
            self.queue.put(steps)

    def kill_traders(self):
        for _ in range(self.n_traders):
            self.queue.put(0)

    def constant_traffic(self, tps):
        self.tps.value = tps
        if self.traffic_maker is None:
            self.traffic_maker = Process(target=make_traffic, args=(self.queue, self.tps))
            self.traffic_maker.start()

    def stop_traffic(self):
        self.tps.value = -1
        self.traffic_maker.join()
        self.traffic_maker = None


def worker(signal_queue, ready_event, dex, phrase, index, set_allowance):
    trader = Trader(dex, f'{phrase}//{index}', report=False, change_port=(9944 + index % 4))
    if set_allowance:
        trader.set_allowances()
    trader.update_balances()
    ready_event.set()
    ok, total = 0, 0
    print(f'Trader {index} ready\n', end='')
    for step in iter(signal_queue.get, 0):
        total += 1
        try:
            result = trader.trade(max_path_len=step)
            if result.is_success:
                ok += 1
        except WebSocketConnectionClosedException:
            trader.chain.connect_websocket()
        except SubstrateRequestException as e:
            msg = e.args[0]
            if msg['message'] == 'Invalid Transaction' and 'account balance too low' in msg['data']:
                print(f'Trader {index} run out of money. Going fishing...\n', end='')
                break
            else:
                raise
    print(f'Trader {index} succeeded in {ok}/{total} swaps\n', end='')


def make_traffic(queue, tps):
    while True:
        begin = time()
        n = tps.value
        if n == -1:
            return
        for _ in range(n - queue.qsize()):
            queue.put(1)
        sleep(1 + begin - time())
