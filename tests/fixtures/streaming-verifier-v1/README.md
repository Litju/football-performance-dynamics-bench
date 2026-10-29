# PR #25 synthetic verifier fixtures

`pr25-synthetic-fixtures.zip` contains synthetic raw inputs and outputs made by a
separately built PR #25 wheel in an isolated virtual environment. The producer
commit is `aad8888eb6c7c046e4dfbce866886bf2ec8dd123`; its pinned source-package
identity is `c3a81aa35599608711be85e3eacd9946bdd762937ef1bd08431a88ba415d20fc`.
The fixture manifest records every input and artifact size and SHA-256. The
archive SHA-256 is `86b1b82e2f14a586df17b18a180f6652bd269dfeaeb57f601ed9aee77bed7671`.

The cases cover ordinary 10 Hz reconstruction, two period grids, a larger
population, absent odd and even source frames, sparse support, 38/41 and 39/41
ball coverage, warnings, partially masked truth, nonzero displacement anchors,
and an incomplete population. These records are synthetic only; the archive has
no SkillCorner source data or production credentials.
