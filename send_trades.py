#!/bin/env python

import re
from argparse import ArgumentParser
from os.path import join
from trade import Dex, Trader, check_file


def get_timings(logfile, skip_first=0):
    regexp = r'.*call.*Ok.(\d+)'
    with open(logfile, encoding='utf-8') as f:
        log = f.read()
    entries = re.findall(regexp, log)[(2 * skip_first):]
    res = []
    for i in range(0, len(entries), 2):
        res.append(int(entries[i + 1]) - int(entries[i]))
    return res


parser = ArgumentParser(prog='send_trades')
parser.add_argument('--router', metavar='AccountId', required=True, help='Router address on chain')
parser.add_argument('--trades', metavar='NUM', type=int, default=10, help='Number of trades to send')
parser.add_argument('--common', metavar='PATH', type=str, default='./common-amm', help='Path to common-amm')
parser.add_argument('--node-log', metavar='PATH', type=str, help='Path to the log of running node')
args = parser.parse_args()
logfile = check_file(args.node_log) if args.node_log else None

metadata_dir = join(args.common, 'artifacts')
metadata_files = {
    'router': check_file(metadata_dir, 'router_contract.json'),
    'factory': check_file(metadata_dir, 'factory_contract.json'),
    'pair': check_file(metadata_dir, 'pair_contract.json'),
    'psp22': check_file(metadata_dir, 'psp22.json')
}

chain_url = 'local'
trader_phrase = '//Alice'

dex = Dex(chain_url, args.router, metadata_files, report=True)
dex.fetch_info()

tr = Trader(dex, trader_phrase)
tr.update_balances()
tr.set_allowances()

for _ in range(args.trades):
    if logfile:
        skip = len(get_timings(logfile, 0))
    tr.trade(1)
    if logfile:
        print(f'Walltime {get_timings(logfile, skip)[0]} ns')
