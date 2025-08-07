import hashlib
import json
import copy
from typing import Dict, Set, List, Tuple, Optional
from ..types.preimage_types import PreimagesTestVector, PreimagesState, PreimageInput
from ..types.enums import PreimageErrorCode


def run_preimage_test(test: PreimagesTestVector) -> bool:
    """Runs a single preimage test and checks if it matches expected output."""
    input_data = test.input
    pre_state = test.pre_state
    output = test.output
    post_state = test.post_state
    name = test.name

    # Check if input is valid
    is_valid, error = check_input(test)
    if not is_valid:
        # Map expected error string to number
        error_map = {
            "preimage_unneeded": PreimageErrorCode.preimage_unneeded,
            "preimages_not_sorted_unique": PreimageErrorCode.preimages_not_sorted_unique,
        }
        expected_error = error_map.get(output.err) if output.err else None
        print(f"Actual error: {PreimageErrorCode(error).name if error is not None else 'none'}")

        if error is not None and expected_error == error:
            # Error matches, check if state is unchanged
            expected = json.dumps(_state_to_dict(post_state), indent=2, sort_keys=True)
            actual = json.dumps(_state_to_dict(pre_state), indent=2, sort_keys=True)
            if expected != actual:
                print("⚔︎⚔︎ State mismatch in error case:")
                print("⇢⇢ Expected:\n", expected)
                print("→→ Got (pre_state):\n", actual)
                return False
            print("✅ Error matched and state unchanged")
            return True  # Test passes for expected error
        
        print(f"🚫 Test failed: Got error {PreimageErrorCode(error).name if error is not None else 'unknown'}, expected {output.err or 'none'}")
        return False

    # Copy state for processing valid preimages
    new_state = copy.deepcopy(pre_state)

    # Process each preimage
    for preimage in input_data.preimages:
        requester = preimage.requester
        blob = preimage.blob
        hash_value = hash_blob(blob)
        blob_length = (len(blob) - 2) // 2  # Hex string length in bytes

        account = None
        for acc in new_state.accounts:
            if acc.id == requester:
                account = acc
                break
        
        if not account:
            print(f"Skipping requester {requester}: account not found")
            continue

        lookup = None
        for entry in account.data.lookup_meta:
            if entry.key.hash == hash_value:
                lookup = entry
                break
        
        if not lookup:
            print(f"Skipping hash {hash_value}: not in lookup_meta")
            continue

        # Add preimage if it's new
        preimage_exists = any(p.hash == hash_value for p in account.data.preimages)
        if not preimage_exists:
            from ..types.preimage_types import PreimagesMapEntry
            account.data.preimages.append(PreimagesMapEntry(hash=hash_value, blob=blob))
            print(f"Added preimage {hash_value} for requester {requester}")

        # Add slot to lookup_meta
        if input_data.slot not in lookup.value:
            lookup.value.append(input_data.slot)
            print(f"Added slot {input_data.slot} for hash {hash_value}")

        # Update stats
        stats = None
        for s in new_state.statistics:
            if s.id == requester:
                stats = s
                break
        
        if not stats:
            from ..types.preimage_types import ServicesStatisticsEntry, StatisticsRecord
            stats = ServicesStatisticsEntry(
                id=requester,
                record=StatisticsRecord(
                    provided_count=0,
                    provided_size=0,
                    refinement_count=0,
                    refinement_gas_used=0,
                    imports=0,
                    exports=0,
                    extrinsic_size=0,
                    extrinsic_count=0,
                    accumulate_count=0,
                    accumulate_gas_used=0,
                    on_transfers_count=0,
                    on_transfers_gas_used=0,
                )
            )
            new_state.statistics.append(stats)
        
        stats.record.provided_count += 1
        stats.record.provided_size += blob_length
        print(f"Updated stats for requester {requester}: count={stats.record.provided_count}, size={stats.record.provided_size}")

    # Sort preimages by hash
    for acc in new_state.accounts:
        acc.data.preimages.sort(key=lambda x: x.hash)

    # Sort accounts by ID
    new_state.accounts.sort(key=lambda x: x.id)

    # Compare final state
    expected = json.dumps(_state_to_dict(post_state), indent=2, sort_keys=True)
    actual = json.dumps(_state_to_dict(new_state), indent=2, sort_keys=True)
    print(f"Actual post_state: {actual}")
    if expected != actual:
        print("⚔︎⚔︎ State doesn't match:")
        print("⇢⇢ Expected:\n", expected)
        print("→→ Got:\n", actual)
        return False

    print("✅ State matches expected")
    return True


def check_input(test: PreimagesTestVector) -> Tuple[bool, Optional[int]]:
    """Validates input: checks for duplicates, sorting, and solicited preimages."""
    input_data = test.input
    pre_state = test.pre_state

    # Check for duplicate hashes per requester and preserve order
    hashes_by_requester: Dict[int, List[str]] = {}
    seen_hashes_by_requester: Dict[int, Set[str]] = {}
    
    for preimage in input_data.preimages:
        requester = preimage.requester
        blob = preimage.blob
        hash_value = hash_blob(blob)
        
        if requester not in hashes_by_requester:
            hashes_by_requester[requester] = []
            seen_hashes_by_requester[requester] = set()
        
        # Check for duplicates
        if hash_value in seen_hashes_by_requester[requester]:
            print(f" Duplicate hash {hash_value} for requester {requester}")
            return False, PreimageErrorCode.preimages_not_sorted_unique
        
        hashes_by_requester[requester].append(hash_value)
        seen_hashes_by_requester[requester].add(hash_value)

    # Check if requesters are sorted
    requesters = [p.requester for p in input_data.preimages]
    if not is_sorted(requesters):
        print(f" Requesters not sorted: {', '.join(map(str, requesters))}")
        return False, PreimageErrorCode.preimages_not_sorted_unique

    # Verify preimages are solicited and not already provided
    for preimage in input_data.preimages:
        requester = preimage.requester
        blob = preimage.blob
        hash_value = hash_blob(blob)
        
        account = None
        for acc in pre_state.accounts:
            if acc.id == requester:
                account = acc
                break
        
        if not account:
            print(f" No account for requester {requester}")
            return False, PreimageErrorCode.preimage_unneeded

        lookup = None
        for entry in account.data.lookup_meta:
            if entry.key.hash == hash_value:
                lookup = entry
                break
        
        if not lookup:
            print(f" Preimage {hash_value} not requested")
            return False, PreimageErrorCode.preimage_unneeded

        preimage_exists = any(p.hash == hash_value for p in account.data.preimages)
        if preimage_exists:
            print(f" Preimage {hash_value} already provided")
            return False, PreimageErrorCode.preimage_unneeded

    # Check if hashes are sorted for each requester
    for requester, hash_list in hashes_by_requester.items():
        sorted_hashes = sorted(hash_list)
        if hash_list != sorted_hashes:
            print(f" Hashes not sorted for requester {requester}: {', '.join(hash_list)}")
            return False, PreimageErrorCode.preimages_not_sorted_unique

    return True, None


def is_sorted(arr: List) -> bool:
    """Checks if an array is sorted in ascending order."""
    for i in range(1, len(arr)):
        if arr[i] < arr[i - 1]:
            return False
    return True


def hash_blob(blob: str) -> str:
    """Computes BLAKE2b-256 hash of a blob."""
    hex_str = blob[2:] if blob.startswith("0x") else blob
    bytes_data = bytes.fromhex(hex_str)
    
    # Use hashlib for BLAKE2b (Python 3.6+)
    hash_obj = hashlib.blake2b(bytes_data, digest_size=32)
    return "0x" + hash_obj.hexdigest()


def _state_to_dict(state: PreimagesState) -> Dict:
    """Convert PreimagesState to dictionary for JSON serialization."""
    return {
        "accounts": [
            {
                "id": acc.id,
                "data": {
                    "preimages": [
                        {"hash": p.hash, "blob": p.blob}
                        for p in acc.data.preimages
                    ],
                    "lookup_meta": [
                        {
                            "key": {"hash": lm.key.hash, "length": lm.key.length},
                            "value": lm.value
                        }
                        for lm in acc.data.lookup_meta
                    ]
                }
            }
            for acc in state.accounts
        ],
        "statistics": [
            {
                "id": stat.id,
                "record": {
                    "provided_count": stat.record.provided_count,
                    "provided_size": stat.record.provided_size,
                    "refinement_count": stat.record.refinement_count,
                    "refinement_gas_used": stat.record.refinement_gas_used,
                    "imports": stat.record.imports,
                    "exports": stat.record.exports,
                    "extrinsic_size": stat.record.extrinsic_size,
                    "extrinsic_count": stat.record.extrinsic_count,
                    "accumulate_count": stat.record.accumulate_count,
                    "accumulate_gas_used": stat.record.accumulate_gas_used,
                    "on_transfers_count": stat.record.on_transfers_count,
                    "on_transfers_gas_used": stat.record.on_transfers_gas_used,
                }
            }
            for stat in state.statistics
        ]
    }
