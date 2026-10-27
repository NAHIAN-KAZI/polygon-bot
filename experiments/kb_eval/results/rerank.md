# Retrieval evaluation: rerank

File `POLYGON_BANK_KNOWLEDGE_BASE_POLYGON.md`, 2121 chunks, embedding model `all-minilm`.

### FAQ questions (named product)

| questions | recall@1 | recall@5 | recall@10 | recall@20 | recall@30 | MRR | median rank | not found |
|---|---|---|---|---|---|---|---|---|
| 101 | 83% | 86% | 93% | 93% | 93% | 0.856 | 1 | 0 |

Worst misses (rank of the first correct chunk):

- 583: Want more details?
  plan: model kept 0 of 30 | queries=['bank products and services overview'] products=['Business banking (overview)', 'Business cards (overview)', 'Personal cards (overview)', 'Business deposit accounts (overview)', 'Personal deposit accounts (overview)'] group=None
- 145: What are the Insurance Benefits ?
  plan: model kept 6 of 30 | queries=['insurance products and benefits', 'bancassurance plans and benefits'] products=['3 Payment Insurance Plan', 'Additional Benefits For Rider', 'Akij Endowment Insurance Plan', 'Akij Takaful DPS Insurance', 'Anticipated Endowment Insurance Plan', 'Bancassurance']... group=Insurance (bancassurance)
- 114: What are Insurance benefits?
  plan: model kept 5 of 30 | queries=['insurance products and benefits', 'bancassurance plans and benefits'] products=['3 Payment Insurance Plan', 'Additional Benefits For Rider', 'Akij Endowment Insurance Plan', 'Akij Takaful DPS Insurance', 'Anticipated Endowment Insurance Plan', 'Bancassurance']... group=Insurance (bancassurance)
- 110: What are the Insurance Benefits?
  plan: model kept 6 of 30 | queries=['insurance products and benefits', 'bancassurance plans and benefits'] products=['3 Payment Insurance Plan', 'Additional Benefits For Rider', 'Akij Endowment Insurance Plan', 'Akij Takaful DPS Insurance', 'Anticipated Endowment Insurance Plan', 'Bancassurance']... group=Insurance (bancassurance)
- 102: What funds can be credited into this account?
  plan: model kept 0 of 30 | queries=['What funds can be credited into a deposit account?', 'deposit account funding sources', 'types of deposits allowed in accounts'] products=['Accounts Current Deposit', 'Accounts Fixed Deposit', 'Accounts Foreign Currency Deposit', 'Accounts Savings Deposit', 'Accounts Scheme Deposit', 'Basic Savings Account']... group=Deposit accounts
- 53: Are there any Other Benefits?
  plan: model kept 2 of 30 | queries=['additional benefits for rider insurance', 'additional benefits for insurance plans'] products=['Additional Benefits For Rider'] group=Insurance (bancassurance)
- 42: Are there Other benefits?
  plan: model kept 3 of 30 | queries=['additional benefits for rider insurance', 'additional benefits for products'] products=['Additional Benefits For Rider'] group=Insurance (bancassurance)
- 9: What are the Dining Benefits?
  plan: model kept 6 of 30 | queries=['Dining benefits for Polygon cards', 'Polygon Mastercard World Elite Credit Card benefits', 'Polygon Islamic Visa Infinite Credit Card benefits'] products=['Polygon Islamic Visa Infinite Credit Card', 'Polygon Mastercard Platinum International Debit Card', 'Polygon Mastercard World Elite Credit Card', 'Visa Infinite', 'Visa Platinum'] group=Cards
- 8: What are 0% interest FlexiBuy program ?
  plan: model kept 6 of 30 | queries=['FlexiBuy program 0% interest details', 'FlexiBuy program eligibility and benefits'] products=[] group=None
- 7: Is joint account allowed?
  plan: model kept 6 of 30 | queries=['joint account eligibility', 'joint deposit account requirements'] products=['Accounts Current Deposit', 'Accounts Fixed Deposit', 'Accounts Foreign Currency Deposit', 'Accounts Savings Deposit', 'Accounts Scheme Deposit', 'Basic Savings Account']... group=Deposit accounts
- 7: What are the Required Documents?
  plan: model kept 6 of 30 | queries=['required documents for opening a bank account', 'required documents for business loan', 'required documents for personal loan'] products=['Agent Banking', 'Business Services Cash Management', 'Business Services Corporate Financing', 'Business Services International Banking', 'Business Services SME Financing', 'Business banking (overview)']... group=None
- 7: What is Membership Rewards program?
  plan: model kept 6 of 30 | queries=['Membership Rewards program benefits', 'Membership Rewards program eligibility'] products=[] group=None
- 6: Whate are the Travel Benefits ?
  plan: model kept 6 of 30 | queries=['travel benefits for credit cards', 'travel benefits for debit cards', 'international travel benefits'] products=['Business cards (overview)', 'Cards Credit', 'Cards Debit', 'Personal cards (overview)', 'Polygon Digital Visa Platinum Debit Card', 'Polygon Islamic Visa Infinite Credit Card']... group=Cards
- 6: What are the Dining Benefits ?
  plan: model kept 6 of 30 | queries=['dining benefits for credit cards', 'Polygon Mastercard World Elite Credit Card benefits', 'Polygon Islamic Visa Infinite Credit Card benefits'] products=['Polygon Islamic Visa Infinite Credit Card', 'Polygon Mastercard Platinum International Debit Card', 'Polygon Mastercard World Elite Credit Card'] group=Cards

### Generic questions

| questions | recall@1 | recall@5 | recall@10 | recall@20 | recall@30 | MRR | median rank | not found |
|---|---|---|---|---|---|---|---|---|
| 39 | 72% | 97% | 97% | 97% | 100% | 0.824 | 1 | 0 |

Worst misses (rank of the first correct chunk):

- 30: How do I apply for a credit card?
  plan: model kept 3 of 30 | queries=['how to apply for a credit card', 'credit card application process', 'credit card eligibility and documents'] products=['Cards Credit', 'Polygon Islamic Visa Infinite Credit Card', 'Polygon Mastercard World Elite Credit Card', 'Polygon Visa SME Credit Card', 'Visa Infinite', 'Visa Platinum'] group=Cards
