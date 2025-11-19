# 🏛️ Windy Civi: OpenCivicData Blockchain Transformer

All actions must do the following

- Be basic scripts in python, bash, rust, or typescript which can run as shell scripts with args.
- Input/output of content should be stdin/stdout, while options can be flags.
- Be have an `action.yml` file that defines the action which uses the shell script to to whatever it needs to.

These scripts should be accessible via the following ways.
- CLI / Unix pipe friendliness where possible
- GitHub Action
- Electron App potentially
