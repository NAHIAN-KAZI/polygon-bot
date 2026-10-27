# Retrieval evaluation: plan

File `POLYGON_BANK_KNOWLEDGE_BASE_POLYGON.md`, 2121 chunks, embedding model `all-minilm`.

### FAQ questions (named product)

| questions | recall@1 | recall@5 | recall@10 | recall@20 | MRR | median rank | not found |
|---|---|---|---|---|---|---|---|
| 101 | 38% | 55% | 59% | 64% | 0.462 | 3 | 0 |

Worst misses (rank of the first correct chunk):

- 850: What are the Required Documents?
  plan: queries=['required documents for opening a bank account', 'required documents for business loan', 'required documents for personal loan'] products=['Agent Banking', 'Business Services Cash Management', 'Business Services Corporate Financing', 'Business Services International Banking', 'Business Services SME Financing', 'Business banking (overview)']... group=None
- 489: Is excise duty applicable?
  plan: queries=['excise duty on bank accounts', 'excise duty on cards', 'fees and charges for excise duty'] products=['Accounts Current Deposit', 'Accounts Fixed Deposit', 'Accounts Foreign Currency Deposit', 'Accounts Savings Deposit', 'Accounts Scheme Deposit', 'Basic Savings Account']... group=Fees, rates and charges
- 425: What are the Dining Benefits?
  plan: queries=['Dining benefits for Polygon cards', 'Polygon Mastercard World Elite Credit Card benefits', 'Polygon Islamic Visa Infinite Credit Card benefits'] products=['Polygon Islamic Visa Infinite Credit Card', 'Polygon Mastercard Platinum International Debit Card', 'Polygon Mastercard World Elite Credit Card', 'Visa Infinite', 'Visa Platinum'] group=Cards
- 314: Can FDR/DPS be opened from this account?
  plan: queries=['eligibility to open fixed deposit or DPS from current account', 'how to open FDR or DPS from a bank account'] products=['Accounts Current Deposit', 'Accounts Fixed Deposit', 'Accounts Foreign Currency Deposit', 'Accounts Savings Deposit', 'Accounts Scheme Deposit', 'Basic Savings Account']... group=Deposit accounts
- 314: How is interest calculated and paid?
  plan: queries=['how is interest calculated and paid on deposit accounts', 'interest payment and calculation methods'] products=['Accounts Current Deposit', 'Accounts Fixed Deposit', 'Accounts Foreign Currency Deposit', 'Accounts Savings Deposit', 'Accounts Scheme Deposit', 'Basic Savings Account']... group=Deposit accounts
- 314: Is tax applicable on the interest?
  plan: queries=['tax on interest income', 'tax applicable on deposit interest', 'interest income tax rates'] products=['Accounts Current Deposit', 'Accounts Fixed Deposit', 'Accounts Foreign Currency Deposit', 'Accounts Savings Deposit', 'Accounts Scheme Deposit', 'Basic Savings Account']... group=Deposit accounts
- 248: What are the Dining Benefits ?
  plan: queries=['dining benefits for credit cards', 'Polygon Mastercard World Elite Credit Card benefits', 'Polygon Islamic Visa Infinite Credit Card benefits'] products=['Polygon Islamic Visa Infinite Credit Card', 'Polygon Mastercard Platinum International Debit Card', 'Polygon Mastercard World Elite Credit Card'] group=Cards
- 226: What funds can be credited into this account?
  plan: queries=['What funds can be credited into a deposit account?', 'deposit account funding sources', 'types of deposits allowed in accounts'] products=['Accounts Current Deposit', 'Accounts Fixed Deposit', 'Accounts Foreign Currency Deposit', 'Accounts Savings Deposit', 'Accounts Scheme Deposit', 'Basic Savings Account']... group=Deposit accounts
- 218: What are the Lifestyle Benefits?
  plan: queries=['lifestyle benefits of Polygon cards', 'card lifestyle benefits'] products=['Business cards (overview)', 'Cards Credit', 'Cards Debit', 'Personal cards (overview)', 'Polygon Digital Visa Platinum Debit Card', 'Polygon Islamic Visa Infinite Credit Card']... group=Cards
- 197: What are the Travel benefits?
  plan: queries=['travel benefits for credit and debit cards', 'international transaction benefits for cards'] products=['Business cards (overview)', 'Cards Credit', 'Cards Debit', 'Personal cards (overview)', 'Polygon Digital Visa Platinum Debit Card', 'Polygon Islamic Visa Infinite Credit Card']... group=Cards
- 191: Want more details?
  plan: queries=['bank products and services overview'] products=['Business banking (overview)', 'Business cards (overview)', 'Personal cards (overview)', 'Business deposit accounts (overview)', 'Personal deposit accounts (overview)'] group=None
- 187: Whate are the Travel Benefits ?
  plan: queries=['travel benefits for credit cards', 'travel benefits for debit cards', 'international travel benefits'] products=['Business cards (overview)', 'Cards Credit', 'Cards Debit', 'Personal cards (overview)', 'Polygon Digital Visa Platinum Debit Card', 'Polygon Islamic Visa Infinite Credit Card']... group=Cards
- 182: What are the Insurance Benefits ?
  plan: queries=['insurance products and benefits', 'bancassurance plans and benefits'] products=['3 Payment Insurance Plan', 'Additional Benefits For Rider', 'Akij Endowment Insurance Plan', 'Akij Takaful DPS Insurance', 'Anticipated Endowment Insurance Plan', 'Bancassurance']... group=Insurance (bancassurance)
- 177: What are Travel Benefits ?
  plan: queries=['travel benefits for credit cards', 'travel benefits for debit cards', 'international travel benefits'] products=['Business cards (overview)', 'Cards Credit', 'Cards Debit', 'Personal cards (overview)', 'Polygon Digital Visa Platinum Debit Card', 'Polygon Islamic Visa Infinite Credit Card']... group=Cards
- 175: What are Dining benefits ?
  plan: queries=['dining benefits for credit cards', 'dining benefits for debit cards'] products=['Business cards (overview)', 'Cards Credit', 'Cards Debit', 'Personal cards (overview)', 'Polygon Digital Visa Platinum Debit Card', 'Polygon Islamic Visa Infinite Credit Card']... group=Cards

### Generic questions

| questions | recall@1 | recall@5 | recall@10 | recall@20 | MRR | median rank | not found |
|---|---|---|---|---|---|---|---|
| 39 | 79% | 95% | 95% | 95% | 0.836 | 1 | 0 |

Worst misses (rank of the first correct chunk):

- 111: What interest do you charge on loans?
  plan: queries=['interest rates on loans', 'lending interest rates'] products=['Auto Loan', 'Business loans (overview)', 'Commercial Housing And Space Finance', 'Digital Nano Loan', 'Distributor Finance', 'Home Loan']... group=Loans and finance
- 22: How do I apply for a credit card?
  plan: queries=['how to apply for a credit card', 'credit card application process', 'credit card eligibility and documents'] products=['Cards Credit', 'Polygon Islamic Visa Infinite Credit Card', 'Polygon Mastercard World Elite Credit Card', 'Polygon Visa SME Credit Card', 'Visa Infinite', 'Visa Platinum'] group=Cards
