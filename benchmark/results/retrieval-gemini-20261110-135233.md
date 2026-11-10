# Retrieval evaluation (gemini, embed model gemini-embedding-2, n=109)

Each example has a held-out paraphrase; the query is the paraphrase and the target is its source example.

| metric | result |
|---|---|
| recall@1 | 97.2% (106/109, 95% CI 92.2 to 99.1) |
| recall@3 | 100.0% (109/109, 95% CI 96.6 to 100.0) |
| recall@5 | 100.0% (109/109, 95% CI 96.6 to 100.0) |
| MRR | 0.986 |

- easy paraphrases: recall@1 98.7% (78/79, 95% CI 93.2 to 99.8), recall@3 100.0% (79/79, 95% CI 95.4 to 100.0), MRR 0.994 (n=79)
- hard paraphrases: recall@1 93.3% (28/30, 95% CI 78.7 to 98.2), recall@3 100.0% (30/30, 95% CI 88.6 to 100.0), MRR 0.967 (n=30)
- claude-draft: recall@1 96.7% (89/92, 95% CI 90.8 to 98.9), recall@5 100.0% (92/92, 95% CI 96.0 to 100.0) (n=92)
- team: recall@1 100.0% (17/17, 95% CI 81.6 to 100.0), recall@5 100.0% (17/17, 95% CI 81.6 to 100.0) (n=17)

Not found at rank 1: 3 of 109.
