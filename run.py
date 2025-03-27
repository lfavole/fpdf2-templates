import importlib
import sys

if __name__ == "__main__":
    program = sys.argv.pop(1)
    importlib.import_module(program, package=".").main()
