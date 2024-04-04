# How to build Common

```
git clone https://github.com/Cardinal-Cryptography/common-amm
cd common-amm
git checkout quick_deploy    ## this branch reduces number of tokens/pairs deployed
make build-and-wrap-all      ## might require cargo-contract 3.2.0, alternatively use make build-and-wrap-all-dockerized
npm run compile
```

# How to deploy Common

Start local chain with default port and then
```
cd common-amm
npm run deploy-local    ##  prints, among others, the router address needed later
npm run spawn-dex-data
```

# How to run trades:

Send 50 single-swap trades from Alice (one trade per block):
```
./send_trades.py --router [ADDR] --trades 50
```