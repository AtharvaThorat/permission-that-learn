"""Demo benchmark entry point: delegates to the shared permission-check CLI."""
import sys
from grids.cli.permissions import main

if __name__ == '__main__':
    main(['check', *sys.argv[1:]])
