# Hooky

[![CI](https://github.com/pydantic/hooky/workflows/CI/badge.svg?event=push)](https://github.com/pydantic/hooky/actions?query=event%3Apush+branch%3Amain+workflow%3ACI)
[![Coverage](https://codecov.io/gh/pydantic/hooky/branch/main/graph/badge.svg)](https://codecov.io/gh/pydantic/hooky)
[![license](https://img.shields.io/github/license/pydantic/hooky.svg)](https://github.com/pydantic/hooky/blob/main/LICENSE)

Receive and respond to GitHub webhooks, built for use with [pydantic](https://github.com/pydantic/pydantic).

## Label and Assign

This tool responds to magic phrases in pull request comments:

* **"please update"** - requests an update from the PR author,
  the PR author is assigned and the "awaiting author revision" label is added
* **"please review"** - requests a review from project reviewers,
  the reviewers are assigned and the "ready for review" label is added

## Change File Checks

This tool checks pull requests to enforce a "change file" has been added.

See [here](https://github.com/pydantic/pydantic/tree/master/changes#pending-changes) for details on the format expected.

To skip this check the magic phrase **"skip change file check"** can be added to the pull request body.

Otherwise, the following checks are performed on the pull request:
* A change file matching `changes/<ID>-<author>.md` has been added
* The author in the change file matches the PR author
* The ID in the change file either matches the PR ID or that issue is marked as closed in the PR body

## Configuration

Hooky is configured via a TOML file in the root of the repository.

Either `.hooky.toml` (takes priority) or `pyproject.toml` can be used, either way the configuration should be under the `[tool.hooky]` table.

The following configuration options are available, here they're filled with the default values:

```toml
[tool.hooky]
reviewers = []  # see below for details on behaviour
request_update_trigger = 'please update'
request_review_trigger = 'please review'
awaiting_update_label = 'awaiting author revision'
awaiting_review_label = 'ready for review'
no_change_file = 'skip change file check'
require_change_file = true
```

**Note:** if `reviewers` is empty (the default), all repo collaborators are collected from [`/repos/{owner}/{repo}/collaborators`](https://docs.github.com/en/rest/collaborators/collaborators).

### Example configuration

For example to configure one reviewer and change the "No change file required" magic sentence, the following configuration could be used:

```toml
reviewers = ['octocat']
no_change_file = 'no change file required'
```
