# route_quality: unlabeled pool v1 (for human labeling)

Written 2026-09-24 by the model. These are **unlabeled**. A human labels them with `wg label new` using
the `kind` rubric in `labels.md`. They are not paraphrases of golden G01–G15 or holdout H01–H20.
The heuristic is **not** scored on this pool until the human labels exist and are frozen.

Known bias: the model that wrote these prompts has read `heuristic.py`. The labeler should be a
human who has not. A later pool should come from real user prompts (Layer-0 logs).

| id | prompt |
|---|---|
| P01 | our docker image is 3GB, can you get it under 500MB |
| P02 | what's a good name for a library that parses dates |
| P03 | bump the lodash version and make sure nothing breaks |
| P04 | the login page shows a blank screen on safari only |
| P05 | which of these two error-handling approaches is more idiomatic in Go? |
| P06 | write me a cover letter for a backend engineer role |
| P07 | set up github actions to run the linter on every push |
| P08 | summarize the main arguments in the attached paper on mixture-of-experts |
| P09 | the p99 latency doubled after yesterday's deploy |
| P10 | sketch the data model for a library book-lending app |
| P11 | does this function leak file handles? |
| P12 | turn this bash script into a python cli |
| P13 | give me a checklist for our first public beta |
| P14 | how many tokens does a 1000-word essay usually come to |
| P15 | port the date utilities from moment to the Temporal API |
| P16 | are there any known CVEs in the version of openssl we pin? |
| P17 | what should I cook tonight with eggs and spinach |
| P18 | our monthly aws bill jumped 40%, where is it coming from |
| P19 | help me decide between sqlite and postgres for a hobby project |
| P20 | make the error messages in the cli friendlier |
| P21 | collect benchmarks people have published for small code models under 3B params |
| P22 | memory usage keeps climbing in the websocket server until it gets OOM-killed |
| P23 | prepare a 5-slide deck explaining our architecture to new hires |
| P24 | teach me how backpropagation works like I'm a programmer, not a mathematician |
| P25 | delete all the dead code in src/legacy |
| P26 | can you double-check my proof that this loop terminates |
| P27 | the migration script ran twice and now there are duplicate rows |
| P28 | draft an email to users about the API deprecation |
| P29 | we need rate limiting on the public API |
| P30 | hi |
