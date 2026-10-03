# Editing and publishing

[Read the website](https://theislampill.github.io/twelve-steps/) · [Builds and deployments](https://github.com/theislampill/twelve-steps/actions/workflows/pages.yml)

The eight root Markdown documents are the reading source. Edit those documents, not
`index.html`. The reader's supplied CSS, JavaScript, layout and navigation style are
preserved in `site/reader.html`. The Python builder supplies the text, section links,
footnotes, table labels and edition metadata. It writes `_site/index.html`.

Every push to `main` runs the tests, builds a fresh reader, verifies its checksums,
and deploys that same artifact to GitHub Pages. Pull requests build and test but
never deploy. A failed test stops publication. The Actions run retains its downloadable
`github-pages` artifact for 30 days; the source remains in Git history.

## First-time Pages setting

In [repository Settings → Pages](https://github.com/theislampill/twelve-steps/settings/pages),
choose **GitHub Actions** as the build and deployment source. This owner-level setting
is separate from committing a workflow. No personal access token needs to be stored
in the repository or sent through a chat. After enabling it, use **Run workflow** on
[Build and deploy reader](https://github.com/theislampill/twelve-steps/actions/workflows/pages.yml),
or push a new commit. The workflow uses GitHub's short-lived deployment credentials.

The target is `https://theislampill.github.io/twelve-steps/`; no custom domain or CNAME
is required. In the repository's About panel, that URL can also be set as Website.
The supplied repository description is retained.

## Local preview

Use Python 3.12 or later. From the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --only-binary=:all: --require-hashes -r requirements.txt
python -m unittest discover -s tests -v
python tools/build_reader.py
python -m http.server 8000 --directory _site
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead. Open
`http://localhost:8000/`, or open `_site/index.html` directly for offline reading.
The page needs no JavaScript packages or network-loaded assets. The external source
links still require a network connection.

## Edition and design changes

`PROVENANCE.json` supplies the edition version and date. Changing a paragraph does
not require a version bump, but a new numbered edition should update the version,
date, notices and changelog consistently. The builder never rewrites the source.

The test suite fingerprints the imported CSS and JavaScript. An intentional design
change must update those two expectations in `tests/test_reader.py` after visual
review. Check both a wide and a mobile layout, keyboard navigation, repeated-note
return links, dark mode and print. Link checks are internal; they do not promise
that external publishers will keep their URLs available.

Dependency versions and wheel hashes are pinned. Review dependency updates against
the reader and tests before merging. CI actions are pinned to commit SHAs. The build
job has read-only repository access; only the main-branch deployment job receives
Pages and OpenID Connect permissions. CODEOWNERS requests the maintainer's review;
it is not a branch-protection rule. A maintainer may require the **Test and build reader**
check on `main` in a repository ruleset.

## Imported edition and checksums

The input was `Twelve_Step_Jurisdiction_v0.13.0.zip` (108,644 bytes), SHA-256:

```text
64cd95988de396441422a7e58d7bc6c85c3ac642ca233b94cc265cdbc277d6be
```

Its Markdown, licence and provenance were checkpointed at
[`0250547`](https://github.com/theislampill/twelve-steps/commit/0250547aefb656b9859ee9a2c24851eb2377d020).
`site/original-v0.13.0.sha256` records the supplied archive's original checksums; it
is a historical receipt, not a manifest of this evolving repository. The imported
`PROVENANCE.json` described a local archive. The current file records the public
repository and the source-checking scope of subsequent editorial editions.

Each generated `_site/SHA256SUMS` covers the newly built HTML and accompanying source
files. From `_site`, run `sha256sum --check SHA256SUMS` to check that artifact. Generated
files are not committed back onto `main`, so editing a document cannot leave a tracked
HTML copy silently stale.
