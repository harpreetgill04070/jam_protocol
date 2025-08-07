
import os
import json
from pathlib import Path
from typing import Dict, Any

from normalize import normalize
from history_stf import HistorySTF
from jam_types import Input, State, BetaBlock, MMR, Reported


def create_input_from_dict(data: Dict[str, Any]) -> Input:
    work_packages = [
        Reported(hash=wp['hash'], exports_root=wp['exports_root'])
        for wp in data.get('work_packages', [])
    ]
    
    return Input(
        header_hash=data['header_hash'],
        parent_state_root=data['parent_state_root'],
        accumulate_root=data['accumulate_root'],
        work_packages=work_packages
    )


def create_state_from_dict(data: Dict[str, Any]) -> State:
   
    beta_blocks = []
    for block_data in data.get('beta', []):
        mmr = MMR(
            peaks=block_data['mmr']['peaks'],
            count=block_data['mmr'].get('count')
        )
        
        reported = [
            Reported(hash=r['hash'], exports_root=r['exports_root'])
            for r in block_data.get('reported', [])
        ]
        
        beta_block = BetaBlock(
            header_hash=block_data['header_hash'],
            state_root=block_data['state_root'],
            mmr=mmr,
            reported=reported
        )
        beta_blocks.append(beta_block)
    
    return State(beta=beta_blocks)


def state_to_dict(state: State) -> Dict[str, Any]:
  
    beta_list = []
    for block in state.beta:
        mmr_dict = {
            'peaks': block.mmr.peaks
        }
        if block.mmr.count is not None:
            mmr_dict['count'] = block.mmr.count
            
        reported_list = [
            {'hash': r.hash, 'exports_root': r.exports_root}
            for r in block.reported
        ]
        
        block_dict = {
            'header_hash': block.header_hash,
            'state_root': block.state_root,
            'mmr': mmr_dict,
            'reported': reported_list
        }
        beta_list.append(block_dict)
    
    return {'beta': beta_list}


def green(msg: str) -> None:
    
    print(f'\033[32m✓ {msg}\033[0m')


def red(msg: str) -> None:
   
    print(f'\033[31m✗ {msg}\033[0m')


def main():
   
    script_dir = Path(__file__).parent
    tiny_dir = script_dir / 'tiny'
    results_dir = script_dir / 'results'
    
    results_dir.mkdir(exist_ok=True)
    
    test_files = sorted([f for f in tiny_dir.iterdir() if f.suffix == '.json'])
    
    current_state = State(beta=[])
    
    for test_file in test_files:
        filename = test_file.name
        output_path = results_dir / filename
        
        try:
            with open(test_file, 'r') as f:
                raw_data = json.load(f)
            
            if 'input' not in raw_data or 'post_state' not in raw_data:
                raise ValueError(f"Missing required keys in {filename}")
            
            input_data = create_input_from_dict(raw_data['input'])
            expected_post_state = create_state_from_dict(raw_data['post_state'])
            
            if 'pre_state' in raw_data:
                current_state = create_state_from_dict(raw_data['pre_state'])
                
        except Exception as e:
            red(f"Failed to parse {filename}: {str(e)}")
            continue
        
        try:
            result = HistorySTF.transition(current_state, input_data)
            post_state = result['postState']
        except Exception as e:
            red(f"STF error in {filename}: {str(e)}")
            continue
        
        is_match = False
        try:
            actual_normalized = normalize(state_to_dict(post_state))
            expected_normalized = normalize(state_to_dict(expected_post_state))
            
            if actual_normalized == expected_normalized:
                is_match = True
        except Exception as e:
            red(f"Comparison error in {filename}: {str(e)}")
            is_match = False
        
        result_data = {
            'input': raw_data['input'],
            'pre_state': state_to_dict(current_state),
            'output': None,
            'post_state': state_to_dict(post_state),
            'verified': is_match
        }
        
        with open(output_path, 'w') as f:
            json.dump(result_data, f, indent=2)
        
        if is_match:
            green(f"{filename} ✅ Test passed")
        else:
            red(f"{filename} ❌ Test failed")
            print("Expected:", json.dumps(expected_normalized, indent=2))
            print("Actual  :", json.dumps(actual_normalized, indent=2))
        
        current_state = post_state


if __name__ == '__main__':
    main()
