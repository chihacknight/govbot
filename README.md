# 🏛️ Windy Civi Toolkit - Tools To Watch & Analyze Governemnt Actions

- Nearly all state governments
- Federal
- (future) Federal Courts
- (future) Executive Orders
- (future) RSS Feeds for news

## Folder Structure

All stuff should be inside `actions`, even if they aren't actions. This functions as the `packages` or `modules` folder in monorepo setups, but the naming convention makes GitHub Actions happy.

## Action Requirements

All actions must do the following

- Be basic scripts in python, bash, rust, or typescript which can run as shell scripts with args.
- Input/output of content should prefer stdin/stdout where it makes sense, while options can be flags.
- Have an `action.yml` file to run as a runner, most likely in GitHub Actions.
- Have snapshot tests that give example outputs of the artifact and/or stdout created by the action.

These scripts should be accessible via the following ways.
- CLI / Unix pipe friendliness where possible
- GitHub Action
- Electron App potentially
