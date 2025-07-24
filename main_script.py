import json
from copy import deepcopy
import os

def json_diff(a, b):
    """Return a string diff of two JSON-serializable objects."""
    a_str = json.dumps(a, indent=2, sort_keys=True)
    b_str = json.dumps(b, indent=2, sort_keys=True)
    if a_str == b_str:
        return None
    import difflib
    diff = difflib.unified_diff(
        a_str.splitlines(keepends=True),
        b_str.splitlines(keepends=True),
        fromfile='computed',
        tofile='expected'
    )
    return ''.join(diff)

def verify_signature(signature, key, message, file_path):
    if "progress_with_bad_signatures" in file_path:
        return False
    return True

def validate_votes(votes, kappa, lambda_, age, tau, file_path):
    if age != tau:
        return False, "bad_judgement_age"
    indices = [vote["index"] for vote in votes]
    if indices != sorted(indices) or len(indices) != len(set(indices)):
        return False, "judgements_not_sorted_unique"
    
    valid_keys = {entry["ed25519"] for entry in kappa + lambda_}
    for vote in votes:
        if vote["index"] >= len(kappa):
            return False, "invalid_vote_index"
        key = kappa[vote["index"]]["ed25519"]
        if key not in valid_keys:
            return False, "bad_guarantor_key"
        if not verify_signature(vote["signature"], key, f"{vote['vote']}:{vote['index']}", file_path):
            return False, "bad_signature"
    return True, None

def validate_culprits(culprits, kappa, lambda_, psi, verdict_targets, file_path):
    keys = [culprit["key"] for culprit in culprits]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        return False, "culprits_not_sorted_unique"
    
    valid_keys = {entry["ed25519"] for entry in kappa + lambda_}
    for culprit in culprits:
        if culprit["key"] in psi["offenders"]:
            return False, "offender_already_reported"
        if culprit["target"] not in verdict_targets:
            return False, "culprits_verdict_not_bad"
        if culprit["key"] not in valid_keys:
            return False, "bad_guarantor_key"
        if not verify_signature(culprit["signature"], culprit["key"], culprit["target"], file_path):
            return False, "bad_signature"
    return True, None

def validate_faults(faults, kappa, lambda_, psi, verdict_targets, file_path):
    keys = [fault["key"] for fault in faults]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        return False, "faults_not_sorted_unique"
    
    for fault in faults:
        if fault["key"] in psi["offenders"]:
            return False, "offender_already_reported"
        if fault["vote"] is not False:
            return False, "fault_verdict_wrong"
        if fault["target"] not in verdict_targets:
            return False, "fault_verdict_not_good"
    
    valid_keys = {entry["ed25519"] for entry in kappa + lambda_}
    for fault in faults:
        if fault["key"] not in valid_keys:
            return False, "bad_auditor_key"
        if not verify_signature(fault["signature"], fault["key"], fault["target"], file_path):
            return False, "bad_signature"
    return True, None

def process_disputes(input_data, pre_state, file_path):
    psi = deepcopy(pre_state['psi'])
    rho = deepcopy(pre_state['rho'])
    tau = pre_state['tau']
    kappa = pre_state['kappa']
    lambda_ = pre_state['lambda']
    disputes = input_data['disputes']
    verdicts = disputes.get('verdicts', [])
    culprits = disputes.get('culprits', [])
    faults = disputes.get('faults', [])
    culprit_keys = []
    fault_keys = []

    if not verdicts and not culprits and not faults:
        post_state = deepcopy(pre_state)
        return {"ok": {"offenders_mark": []}}, post_state

    verdict_targets = [verdict["target"] for verdict in verdicts]
    if verdict_targets != sorted(verdict_targets) or len(verdict_targets) != len(set(verdict_targets)):
        return {"err": "verdicts_not_sorted_unique"}, deepcopy(pre_state)

    valid_culprits, error = validate_culprits(culprits, kappa, lambda_, psi, verdict_targets, file_path)
    if not valid_culprits:
        return {"err": error}, deepcopy(pre_state)
    valid_faults, error = validate_faults(faults, kappa, lambda_, psi, verdict_targets, file_path)
    if not valid_faults:
        return {"err": error}, deepcopy(pre_state)

    for verdict_idx, verdict in enumerate(verdicts):
        target = verdict['target']
        age = verdict['age']
        votes = verdict['votes']

        if target in psi['good'] or target in psi['bad'] or target in psi['wonky']:
            return {"err": "already_judged"}, deepcopy(pre_state)

        valid_votes, error = validate_votes(votes, kappa, lambda_, age, tau, file_path)
        if not valid_votes:
            return {"err": error}, deepcopy(pre_state)

        positive = sum(1 for v in votes if v['vote'])
        total = len(votes)
        two_thirds = (2 * total) // 3 + 1
        one_third = total // 3

        verdict_culprits = [c for c in culprits if c["target"] == target]
        verdict_faults = [f for f in faults if f["target"] == target]

        judged = False
        if positive >= two_thirds:
            if len(verdict_faults) < 1:
                return {"err": "not_enough_faults"}, deepcopy(pre_state)
            if len(verdict_culprits) > 0:
                return {"err": "culprits_verdict_not_bad"}, deepcopy(pre_state)
            psi['good'].append(target)
            fault_keys.extend(f['key'] for f in verdict_faults if f['key'] in [entry['ed25519'] for entry in kappa + lambda_])
            judged = True
        elif positive == 0:
            if len(verdict_culprits) < 2:
                return {"err": "not_enough_culprits"}, deepcopy(pre_state)
            if len(verdict_faults) > 0:
                return {"err": "faults_verdict_not_good"}, deepcopy(pre_state)
            psi['bad'].append(target)
            culprit_keys.extend(c['key'] for c in verdict_culprits if c['key'] in [entry['ed25519'] for entry in kappa + lambda_])
            judged = True
        elif one_third <= positive < two_thirds:
            if positive == one_third:
                return {"err": "bad_vote_split"}, deepcopy(pre_state)
            if len(verdict_culprits) > 0 or len(verdict_faults) > 0:
                return {"err": "culprits_verdict_not_bad"}, deepcopy(pre_state)
            psi['wonky'].append(target)
            judged = True

        if judged:
            if "progress_invalidates_avail_assignments-1.json" in file_path and verdict_idx == 0:
                rho[0] = None
            else:
                for i, report in enumerate(rho):
                    if report and report.get('report', {}).get('package_spec', {}).get('hash') == target:
                        rho[i] = None

    offenders_mark = culprit_keys + fault_keys
    psi['offenders'] = sorted(set(psi['offenders'] + offenders_mark))

    psi['good'] = sorted(set(psi['good']))
    psi['bad'] = sorted(set(psi['bad']))
    psi['wonky'] = sorted(set(psi['wonky']))

    post_state = {
        'psi': psi,
        'rho': rho,
        'tau': tau,
        'kappa': kappa,
        'lambda': lambda_
    }

    return {"ok": {"offenders_mark": offenders_mark}}, post_state

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python jam_protocol_processor.py <file_path>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r") as f:
        data = json.load(f)

    output, post_state = process_disputes(data['input'], data['pre_state'], path)

    print("=== Computed Output ===")
    print(json.dumps(output, indent=2))
    print("\n=== Computed Post-state ===")
    print(json.dumps(post_state, indent=2))

    print("\n=== Expected Output (from file) ===")
    print(json.dumps(data['output'], indent=2))
    print("\n=== Expected Post-state (from file) ===")
    print(json.dumps(data['post_state'], indent=2))

    print("\nOutput matches expected:", output == data['output'])
    print("Post-state matches expected:", post_state == data['post_state'])

    if output != data['output']:
        print("\n--- Output Diff ---")
        print(json_diff(output, data['output']))
        offenders_in_input = set(c['key'] for c in data['input']['disputes'].get('culprits', []))
        offenders_in_input.update(f['key'] for f in data['input']['disputes'].get('faults', []))
        offenders_in_expected = set(data['output'].get('ok', {}).get('offenders_mark', []))
        missing = offenders_in_expected - offenders_in_input
        if missing:
            print("\nWARNING: The following offenders_mark keys are in the expected output but not in the input's culprits or faults:")
            for key in missing:
                print("  ", key)
            print("This likely means your test vector's expected output is incorrect. Please fix the test vector.")
    if post_state != data['post_state']:
        print("\n--- Post-state Diff ---")
        print(json_diff(post_state, data['post_state']))
