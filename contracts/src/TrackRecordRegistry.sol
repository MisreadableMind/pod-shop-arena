// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title TrackRecordRegistry
/// @notice Commitments to track-record snapshots, and a log of who looked.
///
/// Storage holds only the head and a counter. Every historical root lives in
/// events, which cost a fraction of storage and are just as verifiable to
/// anyone reading the log — the chain does not need to answer "what was the
/// root in March" from state when it can prove it from history.
///
/// `seq` is strictly monotonic per record. That is the whole anti-backfill
/// mechanism: a manager who quietly drops a bad month has to leave either a gap
/// in a public sequence or a superseded root that anyone can still read. It
/// only means something if the sequence cannot be tampered with, so the first
/// anchor claims the record and only that address can advance it.
///
/// Why a chain at all, and why this one. We anchor on every ingest and every
/// view, which is only sensible at 0.3s blocks and 0.6s finality. On a
/// twelve-second chain you batch nightly, and the moment you batch you have
/// proved the day rather than the moment — and the moment is the property worth
/// having.
contract TrackRecordRegistry {
    struct Head {
        bytes32 root;
        uint64 seq;
        uint64 ts;
    }

    mapping(bytes32 => Head) private _heads;

    /// @notice Who may advance a record. Set by the first anchor, forever.
    mapping(bytes32 => address) public custodian;

    event Anchored(
        bytes32 indexed recordId,
        bytes32 root,
        uint64 seq,
        uint64 ts,
        address indexed by
    );

    /// @notice A view happened. `viewerCommitment` is keccak(viewerId ‖ salt),
    /// so the chain shows that someone looked and when, without publishing who.
    /// The salt goes to the record owner alone.
    event Accessed(
        bytes32 indexed recordId,
        bytes32 viewerCommitment,
        uint8 profile,
        uint64 ts
    );

    error NotCustodian(bytes32 recordId, address caller, address expected);
    error EmptyRoot();

    /// @notice Commit a new root. Returns the sequence number it was given.
    function anchor(bytes32 recordId, bytes32 root) external returns (uint64 seq) {
        if (root == bytes32(0)) revert EmptyRoot();

        address holder = custodian[recordId];
        if (holder == address(0)) {
            custodian[recordId] = msg.sender;
        } else if (holder != msg.sender) {
            revert NotCustodian(recordId, msg.sender, holder);
        }

        Head storage head_ = _heads[recordId];
        unchecked {
            seq = head_.seq + 1;
        }
        head_.root = root;
        head_.seq = seq;
        // casting to 'uint64' is safe because a unix timestamp does not exceed
        // 2^64 seconds for another 584 billion years
        // forge-lint: disable-next-line(unsafe-typecast)
        head_.ts = uint64(block.timestamp);

        // forge-lint: disable-next-line(unsafe-typecast)
        emit Anchored(recordId, root, seq, uint64(block.timestamp), msg.sender);
    }

    /// @notice Record that a viewer opened a record under a disclosure profile.
    /// Deliberately unpermissioned to write: an access log that only the
    /// platform can append to is an access log the platform can decline to
    /// append to.
    function logAccess(bytes32 recordId, bytes32 viewerCommitment, uint8 profile)
        external
    {
        // forge-lint: disable-next-line(unsafe-typecast)
        emit Accessed(recordId, viewerCommitment, profile, uint64(block.timestamp));
    }

    /// @notice The current commitment for a record.
    function head(bytes32 recordId)
        external
        view
        returns (bytes32 root, uint64 seq, uint64 ts)
    {
        Head storage head_ = _heads[recordId];
        return (head_.root, head_.seq, head_.ts);
    }
}
