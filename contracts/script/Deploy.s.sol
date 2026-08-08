// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {TrackRecordRegistry} from "../src/TrackRecordRegistry.sol";

/// Deploy to Monad Testnet (chain 10143):
///
///   export PODARENA_RPC_URL=https://testnet-rpc.monad.xyz
///   export PODARENA_ANCHOR_PRIVATE_KEY=0x...
///   forge script script/Deploy.s.sol:Deploy \
///     --rpc-url $PODARENA_RPC_URL --broadcast
///
/// Fund the deployer at https://faucet.monad.xyz first.
contract Deploy is Script {
    function run() external returns (TrackRecordRegistry registry) {
        uint256 key = vm.envUint("PODARENA_ANCHOR_PRIVATE_KEY");

        vm.startBroadcast(key);
        registry = new TrackRecordRegistry();
        vm.stopBroadcast();

        console.log("TrackRecordRegistry:", address(registry));
        console.log("chain id:", block.chainid);
        console.log("set PODARENA_REGISTRY_ADDRESS to the address above");
    }
}
