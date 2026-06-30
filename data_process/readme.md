# Test Case Execution Module
The code is used to execute the test cases (Appium) on the virtual machine, and to obtain continuous screenshots, action descriptions, and page descriptions of the steps, which are then used for downstream tasks.

## Environmental requirements
- Dependency library: requirements.txt
- Appium : https://appium.io/docs/zh/2.5/quickstart/
- Android emulator (11.0)
- Python 3.13.5

## How to use
- Place the test cases in CSV format in the directory "data\test_case\test_case.csv". The format is in accordance with the example. 
- Place the installation package in the "DataSet" directory.
- Run the Android emulator
- Start the Appium service
- Run "run.py"