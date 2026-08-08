// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {TrackRecordRegistry} from "../src/TrackRecordRegistry.sol";

contract TrackRecordRegistryTest is Test {
    TrackRecordRegistry internal registry;

    bytes32 internal constant RECORD = keccak256("meridian-global-macro");
    address internal constant MANAGER = address(0xA11CE);
    address internal constant STRANGER = address(0xBAD);

    event Anchored(
        bytes32 indexed recordId, bytes32 root, uint64 seq, uint64 ts, address indexed by
    );

    function setUp() public {
        registry = new TrackRecordRegistry();
    }

    function test_headStartsEmpty() public view {
        (bytes32 root, uint64 seq, uint64 ts) = registry.head(RECORD);
        assertEq(root, bytes32(0));
        assertEq(seq, 0);
        assertEq(ts, 0);
    }

    function test_firstAnchorClaimsAndStartsAtOne() public {
        vm.prank(MANAGER);
        uint64 seq = registry.anchor(RECORD, keccak256("root-1"));

        assertEq(seq, 1);
        assertEq(registry.custodian(RECORD), MANAGER);

        (bytes32 root, uint64 stored, ) = registry.head(RECORD);
        assertEq(root, keccak256("root-1"));
        assertEq(stored, 1);
    }

    /// The sequence is the anti-backfill mechanism, so it has to be strictly
    /// monotonic with no way to reset it.
    function test_sequenceIsStrictlyMonotonic() public {
        vm.startPrank(MANAGER);
        for (uint256 i = 1; i <= 5; i++) {
            uint64 seq = registry.anchor(RECORD, keccak256(abi.encode("root", i)));
            assertEq(seq, uint64(i));
        }
        vm.stopPrank();

        (, uint64 head, ) = registry.head(RECORD);
        assertEq(head, 5);
    }

    /// If anyone could advance somebody else's record, the sequence would prove
    /// nothing — a griefer could manufacture the gaps that are supposed to be
    /// evidence of tampering.
    function test_strangerCannotAdvanceSomeoneElsesRecord() public {
        vm.prank(MANAGER);
        registry.anchor(RECORD, keccak256("root-1"));

        vm.prank(STRANGER);
        vm.expectRevert(
            abi.encodeWithSelector(
                TrackRecordRegistry.NotCustodian.selector, RECORD, STRANGER, MANAGER
            )
        );
        registry.anchor(RECORD, keccak256("hostile"));
    }

    function test_emptyRootRejected() public {
        vm.expectRevert(TrackRecordRegistry.EmptyRoot.selector);
        registry.anchor(RECORD, bytes32(0));
    }

    function test_anchorEmitsHistory() public {
        vm.warp(1_800_000_000);
        vm.expectEmit(true, true, true, true);
        emit Anchored(RECORD, keccak256("root-1"), 1, uint64(1_800_000_000), MANAGER);

        vm.prank(MANAGER);
        registry.anchor(RECORD, keccak256("root-1"));
    }

    /// Two records are independent; one manager's sequence cannot disturb another's.
    function test_recordsAreIndependent() public {
        bytes32 other = keccak256("other-record");

        vm.prank(MANAGER);
        registry.anchor(RECORD, keccak256("a"));
        vm.prank(STRANGER);
        registry.anchor(other, keccak256("b"));

        (, uint64 first, ) = registry.head(RECORD);
        (, uint64 second, ) = registry.head(other);
        assertEq(first, 1);
        assertEq(second, 1);
        assertEq(registry.custodian(other), STRANGER);
    }

    function test_accessLogIsOpenToWrite() public {
        // Deliberately unpermissioned: a log only we can append to is a log we
        // can decline to append to.
        vm.prank(STRANGER);
        registry.logAccess(RECORD, keccak256("viewer-commitment"), 1);
    }

    function testFuzz_anchorAlwaysAdvancesByOne(bytes32[8] calldata roots) public {
        vm.startPrank(MANAGER);
        uint64 expected = 0;
        for (uint256 i = 0; i < roots.length; i++) {
            if (roots[i] == bytes32(0)) continue;
            expected++;
            assertEq(registry.anchor(RECORD, roots[i]), expected);
        }
        vm.stopPrank();
    }
}
