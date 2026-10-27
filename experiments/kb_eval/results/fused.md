# Retrieval evaluation: fused

File `POLYGON_BANK_KNOWLEDGE_BASE_POLYGON.md`, 2121 chunks, embedding model `all-minilm`.

### FAQ questions (named product)

| questions | recall@1 | recall@5 | recall@10 | recall@20 | MRR | median rank | not found |
|---|---|---|---|---|---|---|---|
| 101 | 46% | 67% | 78% | 82% | 0.551 | 2 | 0 |

Worst misses (rank of the first correct chunk):

- 417: Want more details?
  plan: queries=['bank products and services overview'] products=['Business banking (overview)', 'Business cards (overview)', 'Personal cards (overview)', 'Business deposit accounts (overview)', 'Personal deposit accounts (overview)'] group=None
- 169: What are the Insurance Benefits ?
  plan: queries=['insurance products and benefits', 'bancassurance plans and benefits'] products=['3 Payment Insurance Plan', 'Additional Benefits For Rider', 'Akij Endowment Insurance Plan', 'Akij Takaful DPS Insurance', 'Anticipated Endowment Insurance Plan', 'Bancassurance']... group=Insurance (bancassurance)
- 141: What funds can be credited into this account?
  plan: queries=['What funds can be credited into a deposit account?', 'deposit account funding sources', 'types of deposits allowed in accounts'] products=['Accounts Current Deposit', 'Accounts Fixed Deposit', 'Accounts Foreign Currency Deposit', 'Accounts Savings Deposit', 'Accounts Scheme Deposit', 'Basic Savings Account']... group=Deposit accounts
- 141: What are Insurance benefits?
  plan: queries=['insurance products and benefits', 'bancassurance plans and benefits'] products=['3 Payment Insurance Plan', 'Additional Benefits For Rider', 'Akij Endowment Insurance Plan', 'Akij Takaful DPS Insurance', 'Anticipated Endowment Insurance Plan', 'Bancassurance']... group=Insurance (bancassurance)
- 139: What are the Insurance Benefits?
  plan: queries=['insurance products and benefits', 'bancassurance plans and benefits'] products=['3 Payment Insurance Plan', 'Additional Benefits For Rider', 'Akij Endowment Insurance Plan', 'Akij Takaful DPS Insurance', 'Anticipated Endowment Insurance Plan', 'Bancassurance']... group=Insurance (bancassurance)
- 97: What are the Dining Benefits?
  plan: queries=['Dining benefits for Polygon cards', 'Polygon Mastercard World Elite Credit Card benefits', 'Polygon Islamic Visa Infinite Credit Card benefits'] products=['Polygon Islamic Visa Infinite Credit Card', 'Polygon Mastercard Platinum International Debit Card', 'Polygon Mastercard World Elite Credit Card', 'Visa Infinite', 'Visa Platinum'] group=Cards
- 72: Are there any Other Benefits?
  plan: queries=['additional benefits for rider insurance', 'additional benefits for insurance plans'] products=['Additional Benefits For Rider'] group=Insurance (bancassurance)
- 64: What is the Insurance Benefits?
  plan: queries=['insurance products and benefits', 'bancassurance plans and benefits'] products=['3 Payment Insurance Plan', 'Additional Benefits For Rider', 'Akij Endowment Insurance Plan', 'Akij Takaful DPS Insurance', 'Anticipated Endowment Insurance Plan', 'Bancassurance']... group=Insurance (bancassurance)
- 59: What are the Dining Benefits ?
  plan: queries=['dining benefits for credit cards', 'Polygon Mastercard World Elite Credit Card benefits', 'Polygon Islamic Visa Infinite Credit Card benefits'] products=['Polygon Islamic Visa Infinite Credit Card', 'Polygon Mastercard Platinum International Debit Card', 'Polygon Mastercard World Elite Credit Card'] group=Cards
- 47: What are the Travel benefits?
  plan: queries=['travel benefits for credit and debit cards', 'international transaction benefits for cards'] products=['Business cards (overview)', 'Cards Credit', 'Cards Debit', 'Personal cards (overview)', 'Polygon Digital Visa Platinum Debit Card', 'Polygon Islamic Visa Infinite Credit Card']... group=Cards
- 44: What are the Lifestyle Benefits?
  plan: queries=['lifestyle benefits of Polygon cards', 'card lifestyle benefits'] products=['Business cards (overview)', 'Cards Credit', 'Cards Debit', 'Personal cards (overview)', 'Polygon Digital Visa Platinum Debit Card', 'Polygon Islamic Visa Infinite Credit Card']... group=Cards
- 43: What is Insurance benefit ?
  plan: queries=['insurance products and benefits', 'bancassurance plans and benefits'] products=['3 Payment Insurance Plan', 'Additional Benefits For Rider', 'Akij Endowment Insurance Plan', 'Akij Takaful DPS Insurance', 'Anticipated Endowment Insurance Plan', 'Bancassurance']... group=Insurance (bancassurance)
- 38: Are there Other benefits?
  plan: queries=['additional benefits for rider insurance', 'additional benefits for products'] products=['Additional Benefits For Rider'] group=Insurance (bancassurance)
- 34: What is the Double rewards with every swipe ?
  plan: queries=['Polygon Mastercard World Elite Credit Card rewards', 'Polygon Mastercard World Elite Credit Card benefits', 'Double rewards with every swipe'] products=['Polygon Mastercard World Elite Credit Card'] group=Cards
- 30: Is account maintenance fee applicable?
  plan: queries=['account maintenance fees', 'bank account service charges', 'fees and charges for deposit accounts'] products=['Accounts Current Deposit', 'Accounts Fixed Deposit', 'Accounts Foreign Currency Deposit', 'Accounts Savings Deposit', 'Accounts Scheme Deposit', 'Basic Savings Account']... group=Deposit accounts

### Generic questions

| questions | recall@1 | recall@5 | recall@10 | recall@20 | MRR | median rank | not found |
|---|---|---|---|---|---|---|---|
| 39 | 79% | 97% | 97% | 97% | 0.867 | 1 | 0 |

Worst misses (rank of the first correct chunk):

- 26: How do I apply for a credit card?
  plan: queries=['how to apply for a credit card', 'credit card application process', 'credit card eligibility and documents'] products=['Cards Credit', 'Polygon Islamic Visa Infinite Credit Card', 'Polygon Mastercard World Elite Credit Card', 'Polygon Visa SME Credit Card', 'Visa Infinite', 'Visa Platinum'] group=Cards
