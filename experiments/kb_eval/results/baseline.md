# Retrieval evaluation: baseline

File `POLYGON_BANK_KNOWLEDGE_BASE_POLYGON.md`, 2121 chunks, embedding model `all-minilm`.

### FAQ questions (named product)

| questions | recall@1 | recall@5 | recall@10 | recall@20 | recall@30 | MRR | median rank | not found |
|---|---|---|---|---|---|---|---|---|
| 101 | 78% | 86% | 92% | 93% | 95% | 0.828 | 1 | 0 |

Worst misses (rank of the first correct chunk):

- 1429: Want more details?
- 71: What are the Insurance Benefits ?
- 45: Are there Other benefits?
- 44: What are Insurance benefits?
- 42: What are the Insurance Benefits?
- 26: Are there any Other Benefits?
- 21: What funds can be credited into this account?
- 12: Whate are the Travel Benefits ?
- 10: What are the Lifestyle Benefits?
- 10: What is the Insurance Benefits?
- 9: What are the Dining Benefits?
- 8: What are the Dining Benefits ?
- 7: What are the Travel benefits?
- 7: What are 0% interest FlexiBuy program ?

### Generic questions

| questions | recall@1 | recall@5 | recall@10 | recall@20 | recall@30 | MRR | median rank | not found |
|---|---|---|---|---|---|---|---|---|
| 39 | 44% | 74% | 85% | 92% | 97% | 0.561 | 2 | 0 |

Worst misses (rank of the first correct chunk):

- 33: How do I apply for a credit card?
- 27: Can I hold money in dollars?
- 23: What documents are needed for a credit card?
- 19: What interest do you charge on loans?
- 17: What are the eligibility criteria for a Polygon Bank credit card?
- 11: Do you have a card for travelling abroad?
- 7: Who can get a debit card?
- 7: What are the eligibility criteria for a personal loan?
- 6: Do you offer home loans?
- 6: Is there an account for people who work abroad?
