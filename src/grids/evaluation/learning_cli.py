"""`grids learning`: offline synthetic users, recorded predictions and learning comparisons.

  synthesize   write the synthetic world (streams, held-out eval and canary sets) for a seed
  predict      score every distinct input of the given files with the pinned or a local Laya checkpoint
  learn        run every memory and contextual-policy arm on a world with recorded predictions
"""
import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(prog='grids learning', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='operation', required=True)
    synthesize = sub.add_parser('synthesize')
    synthesize.add_argument('--output', required=True)
    synthesize.add_argument('--seed', type=int, default=0)
    synthesize.add_argument('--users', type=int, default=24)
    synthesize.add_argument('--null-users', type=int, default=8)
    synthesize.add_argument('--length', type=int, default=200)
    synthesize.add_argument('--eval-size', type=int, default=600)
    synthesize.add_argument('--canary-size', type=int, default=200)
    predict = sub.add_parser('predict')
    predict.add_argument('--inputs', nargs='+', required=True, help='JSONL files with a laya_input field')
    predict.add_argument('--metadata', required=True, help='local copy of metadata/laya-pairs-v1.json')
    predict.add_argument('--output', required=True)
    predict.add_argument('--model-dir', help='local fine-tuned checkpoint; default is the pinned release')
    predict.add_argument('--method', choices=['rotated', 'single'], default='rotated')
    predict.add_argument('--limit', type=int)
    learn = sub.add_parser('learn')
    learn.add_argument('--world', required=True)
    learn.add_argument('--predictions', required=True)
    learn.add_argument('--output', required=True)
    learn.add_argument('--seeds', type=int, default=20)
    learn.add_argument('--sweep-seeds', type=int, default=10)
    learn.add_argument('--workers', type=int, default=1)
    learn.add_argument('--no-sweep', action='store_true', help='Skip optional parameter sweeps')
    args = parser.parse_args(argv)
    if args.operation == 'synthesize':
        from .synthetic_users import generate, write
        world = generate(args.seed, args.users, args.null_users, args.length, args.eval_size, args.canary_size)
        print(json.dumps({'spec': world['spec'], 'sha256': write(world, args.output)}, indent=2))
    elif args.operation == 'predict':
        from .learning_data import predict_inputs
        print(json.dumps(predict_inputs(args.inputs, args.metadata, args.output, args.model_dir,
                                        method=args.method, limit=args.limit), indent=2))
    elif args.operation == 'learn':
        from .learning_sim import learn as run_learn
        if args.seeds < 1 or args.workers < 1 or (not args.no_sweep and args.sweep_seeds < 1):
            parser.error('Seeds and workers must be positive')
        info = run_learn(args.world, args.predictions, args.output, args.seeds,
                         0 if args.no_sweep else args.sweep_seeds, workers=args.workers)
        print(json.dumps({'output': args.output, 'seeds': info['seeds']}, indent=2))
