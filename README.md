# Hooky

Receive and respond to GitHub webhooks, built for use with [pydantic](https://github.com/pydantic/pydantic).

## Label and Assign

This tool responds to magic phrases in pull request comments:

* **"please update"** - requests an update from the PR author,
  the PR author is assigned and the "awaiting author revision" label is added
* **"please review"** - requests a review from project reviewers,
  the reviewers are assigned and the "ready for review" label is added

## Change File Checks

This tool checks pull requests to enforce a "change file" has been added.

See [here](https://github.com/pydantic/pydantic/tree/master/changes#pending-changes) for details on the format
expected.

To skip this check the magic phrase **"skip change file check"** can be added to the pull request body.

Otherwise, the following checks are performed on the pull request:
* A change file matching `changes/<ID>-<author>.md` has been added
* The author in the change file matches the PR author
* The ID in the change file either matches the PR ID or that issue is marked as closed in the PR body
