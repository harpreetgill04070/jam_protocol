import os
from .stf.run_test import run_preimage_test
from .utils.json_loader import load_test_vector


def main():
    """Main function to run JAM Preimage STF Tests."""
    directories = ["tiny", "full"]
    passed = 0
    failed = 0

    print("** Running JAM Preimage STF Tests:\n")

    for directory in directories:
        # Get the directory of this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_folder = os.path.join(current_dir, f"../test-vectors/{directory}")
        
        if not os.path.exists(test_folder):
            print(f"Warning: Test folder {test_folder} does not exist")
            continue
            
        files = [f for f in os.listdir(test_folder) if f.endswith(".json")]

        print(f"***** Running tests in {directory}:")
        for file in files:
            try:
                test = load_test_vector(directory, file)
                test.name = file  # Add filename to test object
                result = run_preimage_test(test)

                if result:
                    print(f" {file}: Passed")
                    passed += 1
                else:
                    print(f" {file}: Failed")
                    failed += 1
            except Exception as err:
                print(f" {file}: Threw Error")
                print(err)
                failed += 1

    total = passed + failed

    print(f" Passed: {passed}")
    print(f" Failed: {failed}")
    print(f" Total:  {total}")


if __name__ == "__main__":
    main()
