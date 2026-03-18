#!/usr/bin/env python3
"""CLI entrypoint for the OpenHands swarm phase router."""

import argparse
import sys

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", type=str, choices=["sdlc", "creative-writer", "formal-document-writer"], default="sdlc", help="The operating mode of the swarm (default: sdlc).")
    
    # We parse the mode but keep everything else
    args, remaining_argv = parser.parse_known_args()
    
    # To ensure the final help includes --mode, we inject it back or let the router handle it
    # Actually, let's just let the inner routers know what mode they are in by setting an environment variable or just changing their internal parsers directly.
    sys.argv = [sys.argv[0]] + remaining_argv
    
    if args.mode == "creative-writer":
        from trigger_workflow_creative_writer.router import run_trigger_cli
    elif args.mode == "formal-document-writer":
        from trigger_workflow_formal_document_writer.router import run_trigger_cli
    else:
        from trigger_workflow.router import run_trigger_cli

    run_trigger_cli(mode=args.mode)

if __name__ == "__main__":
    main()
