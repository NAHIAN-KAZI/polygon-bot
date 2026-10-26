# Polygon Bank card names: mapping from City Bank PLC

Every card name from the City Bank PLC material in `POLYGON_BANK_KNOWLEDGE_BASE.md`, one row per card page (12 cards; the American Express cards were removed because Polygon will not offer them), with a suggested Polygon name and a suggestion on whether to offer it.
Everything in the Polygon columns is a **suggestion**: change any name and the rest of the file stays valid. Column 3 holds City Bank's own names, exactly as its site writes them.

## Naming rules used

1. **Polygon goes in front.** `Visa Platinum Card` becomes `Polygon Visa Platinum Card`; where City Bank's own name is part of a card name, it becomes Polygon.
2. **City Bank's own sub-brands get a Polygon equivalent:** City Alo becomes Polygon Digital, City Islamic becomes Polygon Islamic, CityGo becomes PolygonGo.
3. **Network and tier names stay:** Visa, Mastercard, UnionPay, TakaPay, and the tiers Platinum, Infinite and World Elite belong to the card networks, not to City Bank.
4. **Business wording is generic:** `City Visa SME Business Credit Card` becomes `Polygon Visa Business Credit Card`.

## 1. Mapping

| # | Card type | City Bank name (original) | Suggested Polygon name | Suggestion | City Bank page |
|---|---|---|---|---|---|
| 1 | Credit - Visa | Visa Platinum Card | Polygon Visa Platinum Card | Yes - core | `/p/visa-platinum` |
| 2 | Credit - Visa | Visa Infinite | Polygon Visa Infinite Credit Card | Yes - core (premium Visa) | `/p-ca/visa-infinite` |
| 3 | Credit - Visa (Islamic) | City Islamic Visa Infinite Credit Card | Polygon Islamic Visa Infinite Credit Card | Only if Polygon runs Islamic banking | `/p-ca/city-islamic-visa-infinite-credit-card` |
| 4 | Credit - Visa (SME) | City Visa SME Business Credit Card | Polygon Visa Business Credit Card | Yes - if Polygon serves small businesses | `/p/city-visa-sme-credit-card` |
| 5 | Credit - Mastercard | Mastercard World Elite Credit Card | Polygon Mastercard World Elite Credit Card | Yes - core (premium Mastercard) | `/p/mastercard-world-elite-credit-card` |
| 6 | Credit - other | CityGo | PolygonGo | Yes - core (everyday cashback card) | `/p-ca/city-go` |
| 7 | Debit | Visa Debit Card | Polygon Visa Debit Card | Yes - core (default debit card) | `/p/visa-debit-card` |
| 8 | Debit | Mastercard Debit Card | Polygon Mastercard Debit Card | Yes - core | `/p/mastercard-debit-card` |
| 9 | Debit | Mastercard Platinum International Debit Card | Polygon Mastercard Platinum International Debit Card | Yes - core (premium debit) | `/p/mastercard-platinum-international-debit-card` |
| 10 | Debit | UnionPay Gold Debit Card | Polygon UnionPay Gold Debit Card | Later - needs scheme membership | `/p/unionPay-gold-debit-card` |
| 11 | Debit | TakaPay Debit Card | Polygon TakaPay Debit Card | Later - needs scheme membership (Bangladesh local scheme) | `/p/takaPay-debit-card` |
| 12 | Debit | City Alo Visa Platinum Debit Card | Polygon Digital Visa Platinum Debit Card | Only if Polygon has a digital-account brand | `/p/city-alo-visa-platinum-debit-card` |

### How the suggestions are grouped

- **Yes - core:** needs only the card network's issuing agreement; these make a complete starter range (Visa and Mastercard premium cards, debit cards, a cashback card).
- **Later - needs scheme membership:** UnionPay and TakaPay are separate payment schemes with their own membership.
- **Only if Polygon runs Islamic banking / has a digital-account brand:** these only apply if Polygon has that line of business.

## 2. Other spellings to replace too

City Bank's site calls some cards by more than one name (list page, product page, fees page). A search-and-replace on the original name alone would miss these.

| Original name | Other spellings found on the site | Replace all with |
|---|---|---|
| Visa Platinum Card | Visa Platinum; VISA Credit Cards (fees page) | Polygon Visa Platinum Card |
| Visa Infinite | City Visa Infinite Credit Card | Polygon Visa Infinite Credit Card |
| City Islamic Visa Infinite Credit Card | City Islamic VISA Infinite Credit Card | Polygon Islamic Visa Infinite Credit Card |
| City Visa SME Business Credit Card | City Bank SME Credit Card; SME Card | Polygon Visa Business Credit Card |
| CityGo | City Go | PolygonGo |
| City Alo Visa Platinum Debit Card | City Alo Visa Debit Card | Polygon Digital Visa Platinum Debit Card |
| UnionPay Gold Debit Card | Union Pay Card | Polygon UnionPay Gold Debit Card |
| TakaPay Debit Card | Taka Pay | Polygon TakaPay Debit Card |

## 3. Brand words inside the card names

For a find-and-replace across the whole knowledge base (these words also appear outside card names).

| Word in the names | Kind | Suggested replacement |
|---|---|---|
| City Bank | the bank's own name | Polygon Bank (inside a card name: Polygon) |
| City Alo | City Bank's digital account brand (its own website, cityalo.com) | Polygon Digital |
| City Islamic | City Bank's Islamic banking brand | Polygon Islamic |
| CityGo / City Go | City Bank product brand | PolygonGo |
| CityTouch | City Bank's digital banking app | PolygonTouch |
| Visa, Mastercard, UnionPay, TakaPay | card networks and payment schemes | keep |

## 4. Notes

- Source: the card list pages and each card's own page on citybankplc.com, collected 2026-10-19.
- `CityGo` is not on City Bank's card list pages, only on its own page; its type (credit) is read from the page text.
- All American Express cards (credit, corporate, gift, prepaid, Islamic and Citymaxx) were removed from this file on request; they are still in `POLYGON_BANK_KNOWLEDGE_BASE.md`.
- Whether a card is offered at all, its limits, fees and eligibility are Polygon's decision; this file only fixes names.

- **Fees and charges:** most card pages carry their own fee table and it is included in each card's section. Fees City Bank publishes only as separate documents could not be fetched (see `POLYGON_BANK_KNOWLEDGE_BASE.md`, last section).
- Section headings below keep City Bank's wording exactly. Text inside a card section is City Bank's, unchanged.

---

# Full card details

Each section is City Bank's text for that card with names changed to the Polygon names from the mapping above:
card names, `City Bank` to `Polygon Bank`, and the sub-brands (City Alo, City Islamic, CityGo, CityTouch, CityCorp).
**Only names were changed.** Every fee, rate, limit, eligibility rule, offer and partner (airlines, hotels, lounges, merchants)
is still City Bank's and must be replaced with Polygon's own before use. Network brands (Visa, Mastercard,
UnionPay, TakaPay) are unchanged. The original City Bank name of each card is in the mapping table and in each section.

Contents:

1. Polygon Visa Platinum Card
2. Polygon Visa Infinite Credit Card
3. Polygon Islamic Visa Infinite Credit Card
4. Polygon Visa Business Credit Card
5. Polygon Mastercard World Elite Credit Card
6. PolygonGo
7. Polygon Visa Debit Card
8. Polygon Mastercard Debit Card
9. Polygon Mastercard Platinum International Debit Card
10. Polygon UnionPay Gold Debit Card
11. Polygon TakaPay Debit Card
12. Polygon Digital Visa Platinum Debit Card

## Card 1: Polygon Visa Platinum Card

- **City Bank original name:** Visa Platinum Card
- **Type:** Credit - Visa
- **Suggestion:** Yes - core

Polygon Bank Visa Platinum Credit Card is now enriched with special offers across dining, shopping, travel, entertainment, and more. Enjoy rewarding experiences, and greater convenience designed to complement your lifestyle.
Cashback worth BDT 500
Earn 1 MyRewards Point for every BDT 50 spent
Buy 1 Get 1 Complimentary Companion Buffet

### Welcome Offer
Cashback worth BDT 500 
Minimum online spend of BDT 5,000 required to avail the offer

Note : Cardmembers will enjoy a BDT 500 cashback on a single online purchase transaction of BDT 5,000 or above. Validity: Within 60 days of card issuance.

### Travel Benefits
Enjoy 10% savings on Shohoz bus tickets 
Maximum savings: BDT 100 per transaction

### Lifestyle Benefits
Buy 1 Get 1 Complimentary Companion Buffet: Cardmembers can enjoy Buy 1 Get 1 complimentary companion buffet throughout the week or on weekends, depending on participating partners:

All Week Partners(Upon Availability):

Six Seasons Hotel
Hotel Sarina
Golden Tulip The Grandmark

Weekend Partners:

Beyond Buffet, Dhaka
FARS Hotel & Resorts, Dhaka
Grand Sylhet Hotel & Resort, Sylhet

### Required Documents
For Salaried Person:

Latest Salary Certificate / Last 3 Months Pay Slip
Latest income tax return certificate/ acknowledgement receipt
E-Tin Certificate Copy
Valid Passport Copy
Office ID Card Copy
Bank Statement Last 6 Months
Business Card
2 Copy LAB Print Photo
NID Photocopy

 

For Business Person:

Trade License Or Partnership Deed Copy ( For Partnership Concern ) or Or MOA + ARTICLE 10 & 12 ( For Limited Company )
E-Tin Certificate Copy
Valid Passport Copy
Bank Statement Last 12 Months
Business Card
2 Copy LAB Print Photo
NID Photocopy

### Fees and Charges
Please click here to download fees and charges

### Polygon Bank Card Offers

### Insurance Benefits
Double Benefit Insurance (DBI)

Provides coverage against the outstanding card balance in the event of death or permanent total disability (PTD). The benefit settles the outstanding balance and pays an equal amount to the nominee.

Maximum payout: BDT 2,000,000 or twice the outstanding balance, whichever is lower
Premium: 0.40% of the monthly outstanding balance

Critical Care Insurance (CCI)

Coverage for 18 critical illnesses, including:

Cancer
Stroke
Myocardial Infarction
Renal Failure
Paralysis
Coronary Artery Surgery
Major Organ Transplant
Blindness
Heart Valve Replacement
Surgery for Diseases of the Aorta
Multiple Sclerosis
Aplastic Anemia
Benign Brain Tumor
End-Stage Lung Disease
Major Head Trauma
Complete Deafness
Loss of Limbs
Loss of Speech

### Additional Privileges
Flexi loan
 0% interest FlexiBuy program
Card cheque
Balance transfer
Equal monthly instalments
24-hour dedicated customer service center
E-statements
Card replacement
Outstanding balance EMI

### MyRewards Points
Earn 1 MyRewards Points upon spending BDT 50 or USD1

Cardmembers can waive their annual fee through MyRewards Points:

 

| Visa Platinum | Annual Fee Amount in BDT | Required Points |
|---|---|---|
| 25% Annual Fee | 750 | 1875 |
| 50% Annual Fee | 1500 | 3750 |
| 75% Annual Fee | 2250 | 5625 |
| 100% Annual Fee | 3000 | 7500 |

Terms & Condition: MyRewards Points are earned only on eligible e-commerce and POS transactions. Reward Points earning is not applicable to transactions made through MFS/Digital wallets, Fuel stations, Government fees and services.

Source (City Bank page): https://www.citybankplc.com/p/visa-platinum

---

## Card 2: Polygon Visa Infinite Credit Card

- **City Bank original name:** Visa Infinite
- **Type:** Credit - Visa
- **Suggestion:** Yes - core (premium Visa)

Be Boundless Be Infinite
City Visa Infinite and Polygon Islamic Visa Infinite Credit Cards offer a range of premium benefits designed to enhance everyday lifestyle and travel experiences. Cardmembers can enjoy airport lounge access, dining privileges, cashback rewards, travel assistance, and exclusive discounts on shopping, hotels, and entertainment. The cards also come with comprehensive insurance coverage and other benefits to complement their lifestyle and travel needs. MyRewards points are available only with the Polygon Islamic Visa Infinite Credit Card.
Explore A World of Infinite Benefits
Welcome Voucher
Start every year of your Cardmembership with rewards tailored to your lifestyle. Enjoy an exclusive BDT 10,000 welcome gift voucher.
Buy 1 Get 1 Buffet
Complementary buffet at renowned 5-star hotels
Visa Global Privileges
Up to 15% discounts on shopping, dining, hotels and many more
Rewards on every purchase
Enjoy BDT 1,000 cashback monthly for 3 months on BDT 25,000 spend. Afterwards, City Visa Infinite conventional Cardmembers earn 1% cashback up to BDT 12,000/year; Polygon Islamic Cardmembers earn 3 MyRewards points per BDT 100/USD 1...
LoungeKey Access
Upto 8 complementary visit to over 1800 international airport lounges every year.
Access to Polygon Bank Airport Lounges
Unlimited access to Polygon Bank lounges at Dhaka International Airport/Domestic Airport

### What are the major benefits of Polygon Visa Infinite Credit Card?
Polygon Visa Infinite Credit Card offer you up to 45 days of additional charges free periods, wide acceptance, B1G1 buffet offer, complementary lounge access, and other benefits. Details shared below:

 

BDT 10,000 Air Ticket voucher as a welcome gift. Service Provider: GoZayaan and ShareTrip.
Unlimited access to Polygon Bank International and Domestic Lounge at Hazrat Shahjalal International Airport, Dhaka. Combination of cardholder with 1 adult & 2 children per visit. Supplementary cardholder can access the lounge with 1 adult & 2 children per visit. (Lounge access is applicable for departure time only).
Complimentary Meet & Greet services while Departure/Arrival at Hazrat Shahjalal International Airport, Dhaka. Cardmembers can take one (1) family member with them complimentary (yearly 5 times).

Dining Benefits - Enjoy complimentary buffet offers at selected partner hotels, including:

AMARI DHAKA
INTERCONTINENTAL DHAKA
LE MERIDIEN DHAKA
RADISSON BLU DHAKA WATER GARDEN
RADISSON BLU CHATTOGRAM BAY VIEW
THE WESTIN DHAKA
SHERATON DHAKA
THE PENINSULA
PAN PACIFIC SONARGAON
HOLIDAY INN DHAKA
CROWNE PLAZA DHAKA GULSHAN
ROSE VIEW HOTEL
CROWNE PLAZA DHAKA AIRPORT
RENAISSANCE
LAKESHORE GRAND
HYATT PALACE UTTARA

### Who are eligible to apply for Polygon Visa Infinite Credit Card?
Any Bangladeshi Resident is eligible to apply for a Polygon Visa Infinite Credit Card.

### How many supplementary card can I avail?
As a Visa Infinite Cardmember, you can avail 1 (one) supplementary credit card for free. Any more than that, you will incur 50% of the annual fee.

### Who are eligible to avail welcome gift vouchers?
Only primary cardmembers are allowed to avail the welcome gift vouchers; supplementary cardmembers cannot avail them.

### Required Documents
For Salaried Person:

Latest Salary Certificate / Last 3 Months Pay Slip
Latest income tax return certificate/ acknowledgement receipt
E-Tin Certificate Copy
Valid Passport Copy
Office ID Card Copy
Bank Statement Last 6 Months

For Business Person:

Trade License or Partnership Deed Copy (For Partnership Concern) or MOA + ARTICLE 10 & 12 (For Limited Company)
E-Tin Certificate Copy
Valid Passport Copy
Office ID Card Copy

### Fees and Charges
Fees & Charges

### Polygon Bank Card Offers

### LoungeKey FAQ
8 complimentary LoungeKey  Accesses in the international lounges per year. After 8 visits, regular access fee will be charged.  Supplementary cardmember will get complimentary LoungeKey membership  but to get access in the lounge  USD 35 will be charged. Primary cardmember must be present to avail this offer.

Note: LoungeKey  can only be used at foreign airport lounges and after the complimentary lounge access, lounge access fee of USD 35 will be applicable.

LoungeKey Website

To explore participating airport lounges and exclusive travel benefits available through your Polygon Bank Polygon Visa Infinite Credit Card, please visit: www.loungekey.com/citybankvisainfinite  

You may also create your personal LoungeKey account through this dedicated Website. Simply register using your eligible Polygon Bank Polygon Visa Infinite Credit Card details and create your User ID and Password. The same credentials can be used to access both the LoungeKey website and the LoungeKey mobile application.

LoungeKey Mobile App

For quick and convenient access to participating airport lounges worldwide, download the LoungeKey app from the Google Play Store or Apple App Store.

 

To learn more click here.

### Insurance Benefit
Double Benefit Insurance (DBI): Double Benefit Insurance (DBI) insures your outstanding balance during unfortunate events of death or permanent total disability (PTD) by paying off your full outstanding balance and an equal amount to your nominee. The maximum payout amount will not exceed BDT 2,000,000 or twice the outstanding amount, whichever is lower. Once you get enrolled in the program, you will be charged a premium of 0.40% on your monthly card outstanding balance.

The Critical Care Insurance program allows Cardmembers to receive benefit of treatment of 18 different critical diseases:

| Serial No | Disease | Serial No | Disease | Serial No | Disease |
|---|---|---|---|---|---|
| 1. | Cancer | 7. | Major Organ Transplant | 13. | Benign Brain Tumor |
| 2. | Stroke | 8 . | Blindness | 14. | End Stage of Lung Disease |
|  | End Stage of Lung Disease |  |  |  |  |
| 3. | Myocardial Infraction | 9. | Heart Valve Replacement | 15. | Major Head Trauma |
| 4. | Renal Failure | 10. | Surgery for Disease of Aorta | 16. | Complete Deafness |
|  | Complete Deafness |  |  |  |  |
| 5. | Paralysis | 11. | Multiple Sclerosis | 17. | Loss of Limbs |
| 6. | Coronary Artery Surgery | 12. | Aplastic Anemia | 18. | Loss of Speech |

 

For the Polygon Visa Infinite Credit Card, the maximum coverage Cardmembers would receive per year under the Critical Care program is BDT 200,000.

### Airline offers
Air Astra

 

| Details | Information |
|---|---|
| Savings | 10% on base fare |
| Routes | Domestic |
| Platforms | Air Astra Sales Outlets only |
| Validity | Till 31st December ,2026 |
| Contact | Hotline: 13607 |
| T&C | The offer is applicable for Polygon Bank Visa Infinite Credit Cards The savings offer is valid for POS transactions only The offer is applicable on the base fare only and is not inclusive of taxes or other charges Clubbing this offer with any other promotional offers or packages is at the sole discretion of the partner Refund, booking and cancellation policies are subject to the rules and regulations of Air Astra Other terms and conditions may apply |

 

US Bangla Airlines

 

| Details | Information |
|---|---|
| Savings | 15% on base fare on domestic route 10% on base fare of international route |
| Routes | Domestic & International |
| Platforms | www.usbair.com, US-Bangla App: 15% on domestic & 10% on international Sales Outlets :10% savings on both domestic and international flight tickets at US- Bangla nominated sales outlets. |
| Promo Code | USBA15 (Domestic), USBAIN10 (International) |
| Validity | Till 31st December ,2026 |
| Contact | Hotline: 13605 |
| T&C | Savings offer is applicable for adult and children's tickets only and excludes tickets for infants (0-2 years) Tickets sold under this campaign are non-refundable (date changes are allowed as per policy of US-Bangla Airlines) Cardmember has to be a traveler in order to avail the offer and maximum 04 tickets (including parents, spouse & children of the Cardmember) can be purchased in a single transaction The offer cannot be clubbed with any other offers Polygon Bank Visa Infinite Cardmember can enjoy savings on base fare for all available routes Savings offer will not be applicable for traveling on blackout dates, which are subject to the discretion of the partner The offer can be availed from www.usbair.com or the US-Bangla Airlines app using the promo codes "USBA15" for domestic air tickets and "USBAIN10" for international air tickets |

 

Biman Bangladesh

 

| Details | Information |
|---|---|
| Savings | 10% (outlets), 7% (online) on base fare |
| Routes | Domestic & International (originating from Bangladesh) |
| Platforms | Sales outlets, www.biman-airlines.com, Biman App |
| Promo Code | ‘BGWEB2026’ (for online) |
| Validity | Till 31 December 2026 |
| T&C | This offer is applicable for both inbound and outbound journeys Polygon Bank cardmembers can purchase a maximum of 4 tickets per transaction using a debit or credit card The offer is valid on a minimum base fare of BDT 2,500 for one-way tickets and BDT 5,000 for round-trip tickets (per ticket) Cardmembers can enjoy 10% savings at nominated sales outlets of Biman Bangladesh Airlines Online customers can enjoy 7% savings by booking through both www.biman-airlines.com and the Biman Bangladesh Mobile App using the promo code 'BGWEB2026' The offer is not applicable for Umrah tickets The offer is not applicable for infant tickets Other terms and conditions may apply at the discretion of Biman Bangladesh Airlines |

 

Novo Air

 

| Details | Information |
|---|---|
| Savings | 10% on base fare |
| Routes | Domestic & International |
| Platforms | www.flynovoair.com, NOVOAIR App, Sales Outlets |
| Promo Code | VQCBW (for online purchases) |
| Validity | Till 31 December 2026 |
| T&C | Cardmembers can avail the offer from www.flynovoair.com, NOVOAIR app or NOVOAIR sales outlets Tickets need to be used within the travel validity period. The travel validity period will be 6 months from the date of purchase Offer is applicable for Polygon Visa Infinite Credit Card Offer is applicable on the base fare only. No savings will be offered on taxes & other charges This offer can’t be combined with any other ongoing offer of NOVOAIR The service delivery, refund and exchange policies are set as per the rules and regulations of NOVOAIR |

### Additional Privileges
Flexi Loan/Flexi Cash

PolygonTouch Internet Banking
Card Cheque
Fund Transfer
24-hour dedicated Customer Service Center
E-Statements
Card Replacement

### My Rewards Points for Polygon Islamic Visa Infinite Credit Card
Earn 3 MyRewards Points upon spending BDT 100 or USD1

Cardmembers can waive their annual fee through MyRewards Points:

| VISA Islamic Infinite | Item Code | Value(BDT) | Required Points |
|---|---|---|---|
| 25% Annual Fee - VISA Islamic Infinite | FE1154 | 2,500 | 6,250 |
| 50% Annual Fee - VISA Islamic Infinite | FE1155 | 5,000 | 12,500 |
| 75% Annual Fee - VISA Islamic Infinite | FE1156 | 7,500 | 18,750 |
| 100% Annual Fee - VISA Islamic Infinite | FE1157 | 10,000 | 25,000 |
| Captured Card Replacement Fees - VISA Islamic Infinite | FE1158 | 350 | 1,200 |
| Card Replacement Fees - VISA Islamic Infinite | FE1159 | 850 | 3,000 |
| Late Payment Fees - VISA Islamic Infinite | FE1160 | 1,000 | 3,500 |
| Over Limit Fees - VISA Islamic Infinite | FE1161 | 1,500 | 5,250 |

 

Terms & Condition: MyRewards Points are earned only on eligible e-commerce and POS transactions. Reward Points earning is not applicable to transactions made through MFS/Digital wallets, Fuel stations, Government fees and services.

Source (City Bank page): https://www.citybankplc.com/p-ca/visa-infinite

---

## Card 3: Polygon Islamic Visa Infinite Credit Card

- **City Bank original name:** City Islamic Visa Infinite Credit Card
- **Type:** Credit - Visa (Islamic)
- **Suggestion:** Only if Polygon runs Islamic banking

Be boundless Be infinite
Experience a premium lifestyle while following Shariah-compliant financial principles. Enjoy exclusive privileges across travel, dining, and rewardswithout compromising your values.
Explore A World of Infinite Benefits
Welcome Gift
BDT 10,000 air ticket voucher (redeemable via ShareTrip or GoZayaan)
Buy 1 Get 1 Buffet
Enjoy complimentary buffet offers at selected partner hotels
LoungeKey Access
Up to 8 complimentary visits per year to 1,700 international airport lounges
Visa Global Privileges
Enjoy up to 50% off
Cashback Offer
BDT 1,000 cashback per month
Polygon Bank Airport Lounges
Unlimited access at Dhaka International & Domestic Airports

### Eligibility
Salaried: Minimum monthly income BDT 60,000
Business/Other: Minimum monthly income BDT 100,000
Primary Cardholder: 21–65 years (CityShield mandatory if above 60)
Supplementary Cardholder: 18–65 years

### Financial Features
Annual Fee: BDT 10,000 + VAT
Credit Limit:
Unsecured: BDT 1.2 lakh – 20 lakh
Secured: BDT 60,000 – 40 lakh

### Additional Privileges
Flexi Loan & Balance Transfer
0% Interest FlexiBuy & EMI Facility
EasyPay & 24/7 Customer Service
E-Statements & Card Replacement

### Required Documents
Salaried Individuals

Salary certificate / last 3 months’ payslips
Income Tax Return / e-TIN Certificate
Passport & Office ID
Bank Statement (6 months)
2 passport-size photos, NID Copy, KYC Form

Business Individuals

Trade License / Partnership Deed / MOA & Articles
Passport Copy
Bank Statement (12 months)

### Fees and Charges
Download here

### What are the major benefits of Polygon Visa Infinite Credit Card?
Welcome Gift

Buy 1 Get 1 Buffet

Enjoy complimentary buffet offers at selected partner hotels, including:

Amari Dhaka
InterContinental Dhaka
Le Méridien Dhaka
Radisson Blu Dhaka Water Garden
Radisson Blu Chattogram Bay View
The Westin Dhaka
Renaissance Dhaka
The Peninsula Chattogram
Pan Pacific Sonargaon Dhaka
Holiday Inn Dhaka
Crowne Plaza Gulshan
Crowne Plaza Airport
Rose View Hotel
Hyatt Place Uttara

LoungeKey Access

Up to 8 complimentary visits per year to 1,700 international airport lounges.

Visa Global Privileges

Enjoy up to 50% off on shopping, dining, hotels, and more worldwide
Learn more: Visa Offers & Perks

Cashback Offer

BDT 1,000 cashback per month for the first 3 months
Minimum monthly spend: BDT 25,000

Polygon Bank Airport Lounges

Covers cardholder + partner + 2 children per visit

MyRewards Points

Earn 3 points for every BDT 100 or USD 1 spent

Insurance Benefits

Double Benefit Insurance (DBI)

Covers outstanding balance in case of death or Permanent Total Disability (PTD)
Payout: Full outstanding balance + equal amount to nominee (max BDT 2,000,000)
Premium: 0.40% of monthly outstanding balance

Critical Care Insurance (CCI)

Coverage for 18 critical illnesses, including: Cancer, Stroke, Heart Attack, Renal Failure, Paralysis, Major Organ Transplant, Heart Valve Replacement, Blindness, and more.

Source (City Bank page): https://www.citybankplc.com/p-ca/city-islamic-visa-infinite-credit-card

---

## Card 4: Polygon Visa Business Credit Card

- **City Bank original name:** City Visa SME Business Credit Card
- **Type:** Credit - Visa (SME)
- **Suggestion:** Yes - if Polygon serves small businesses

Polygon Visa Business Credit Card
An SME business credit card designed specifically for CMSMEs to manage day-to-day business expenses with ease. Make regulatory, tax, and statutory payments seamlessly without disrupting cash flow. Use it confidently for both domestic and international business needs.

### Travel Benefits
Lounge Access:
•⁠  ⁠First Year: 1 complimentary Polygon Bank International Lounge visit and 2 complimentary Polygon Bank Domestic Lounge visits
•⁠  ⁠Second Year Onwards: Complimentary Polygon Bank International and Domestic Lounge visits can be redeemed using Loyalty Points (Gold Lounge only)

Exclusive Facilities:
Manage commute, travel, and employee expenses with an additional USD 3,000 SME limit for SME Foundation-registered businesses:

•⁠  ⁠Additional limit for international business travel
•⁠  ⁠Airline benefits for frequent travel to key trade destinations, including China
•⁠  ⁠Easy card payments for international fair and exhibition registrations

### MyRewards Points
1 MyRewards Points for every BDT 50 and USD 1 spent
Redeem points to pay below fees and charges :

| Annual Fees/Other Charges |  | Item Code | Gift Value in BDT | Points Required |
|---|---|---|---|---|
| VISA SME | 25% Annual Fee - VISA SME | FE1125 | 750 | 1,875 |
| VISA SME | 50% Annual Fee - VISA SME | FE1126 | 1,500 | 3,750 |
| VISA SME | 75% Annual Fee - VISA SME | FE1127 | 2,250 | 5,625 |
| VISA SME | 100% Annual Fee - VISA SME | FE1128 | 3,000 | 7,500 |
| VISA SME | Captured Card Replacement Fees-VISA SME | FE1129 | 350 | 1,200 |
| VISA SME | Card Replacement Fees-VISA SME | FE1130 | 500 | 1,750 |
| VISA SME | Late Payment Fees-VISA SME | FE1131 | 600 | 2,150 |
| VISA SME | Over Limit Fees-VISA SME | FE1132 | 1,000 | 3,500 |

### Business Expenses That Work for Your SME
Government & Statutory Payments

Tax & VAT payments
Legal, licensing & regulatory fees
Insurance premiums

Business Operations

Utility bills
Office rent & maintenance
Supplier & vendor payments
Internet & mobile bills

Marketing & Digital Spend

Advertising & promotion costs
Online & e-commerce payments
Digital tools & subscription services

Travel & Mobility

Local transportation & accommodation
International business travel expenses
Fair, exhibition & trade registration payments

Emergency & Contingency Expenses:

Medical & hospitalization expenses for cardholders
Upto 25% cash withdrawal for emergency business expenses

### Insurance Benefits
Double Benefit Insurance (DBI):
Covers your outstanding balance in case of death or permanent total disability (PTD), and pays an equal amount to your nominee. Maximum payout: BDT 2,000,000 or twice the outstanding balance, whichever is lower. Premium: 0.40% of monthly outstanding balance.

Critical Care Insurance (CCI):
Provides benefits for 18 critical illnesses:

Cancer
Stroke
Myocardial Infarction
Renal Failure
Paralysis
Coronary Artery Surgery
Major Organ Transplant
Blindness
Heart Valve Replacement
Surgery for Diseases of the Aorta
Multiple Sclerosis
Aplastic Anemia
Benign Brain Tumor
End-Stage Lung Disease
Major Head Trauma
Complete Deafness
Loss of Limbs
Loss of Speech

For the Visa SME Credit Card, the maximum coverage Cardmembers would receive per year under the Critical Care program is BDT 150,000.

### 0% Interest FlexiBuy Program
Make purchases at 0% interest with instalment plans ranging from 3 to 36 months.

### Visa Global Offers
Click here to view Visa Global Offers

### Fees and Charges

Source (City Bank page): https://www.citybankplc.com/p/city-visa-sme-credit-card

---

## Card 5: Polygon Mastercard World Elite Credit Card

- **City Bank original name:** Mastercard World Elite Credit Card
- **Type:** Credit - Mastercard
- **Suggestion:** Yes - core (premium Mastercard)

Experience an elevated lifestyle, world-class travel benefits, and more with the Polygon Bank Polygon Mastercard World Elite Credit Card.
Exclusive welcome and yearly gifts
Premium travel and airport privileges
Lifestyle and dining offers
Complimentary global lounge access
Reward points and cashback benefits
### Features
Mastercard World Elite Global Offers
Global travel and lifestyle privileges
Unlimited Polygon Bank lounge access
LoungeKey™ international lounge access
Flexible payment solutions
Reward points on every spend
Insurance protection and global offers

### More Benefits
Cashback:

Get 10% cashback on movie tickets at Star Cineplex locations across Bangladesh.

*Minimum transaction should be BDT 500 and monthly eligible cashback amount is BDT 500. This offer can be avail through Online and Offline both; Can only be avail through Polygon Bank POS *

Investment Advisory:

Access personalized investment advisory services from City Brokerage Ltd.

Travel Benefits:

Meet & Greet Service

Unlimited Meet & Greet assistance available for primary cardmembers + 2 companions per visit. For any additional person beyond the entitled limit will be charged BDT 500 per person (to immigration point only). Charges for additional passenger must be settled on spot by Travel Shop Ltd. representative.  

Cardmembers may book the Meet & Greet service for both Departure/Arrival at Hazrat Shahjalal International Airport, Dhaka. To avail this service, cardmembers need to call at 01841330303, 01777775584 or email travelshop.airport@gmail.com minimum 12 hours before arrival or departure. Customer can avail this service through PolygonTouch as well.

 

Polygon Bank Lounge Access

Unlimited access to Polygon Bank lounges (domestic & international) for:

Primary cardmember + 1 adult + 2 children per visit
Supplementary cardmembers: 1 adult + 2 children per visit

Special Travel Discounts

Saimon Holidays: Complimentary visa assistance support and up to 12% savings
Bhawal Resort: 40% savings on weekday stays
Dream Square Resort: Up to 45% savings on resort stays

### MyRewards Points
Reward Points:

Earn 2 points per BDT 50 spends
Earn 4 points per USD 1 spends

10X Reward Weekends:
Earn 10X Reward Points on first and last weekends of each month at:

Apon Family Mart, CSD Bangladesh, DSS Adi New, Khulshi Mart, Lavender, Prince Bazar, Unimart

*This offer can only be avail through Polygon Bank POS*

Activation Bonus:
5,000 bonus points on a minimum spends of BDT 60,000 within 2 months of card issuance 

Primary Cardmember will only eligible for this bonus

Terms & Condition: MyRewards Points are earned only on eligible e-commerce and POS transactions. Reward Points earning is not applicable to transactions made through MFS/Digital wallets, Fuel stations, Government fees and services

### Insurance Benefits
Double Benefit Insurance (DBI): Covers outstanding balance in case of death or permanent total disability (PTD) and pays an equal amount to your nominee. Maximum payout: BDT 2,000,000 or twice the outstanding balance, whichever is lower. Premium: 0.40% of monthly outstanding balance.

All Accidental Death Insurance (AADI): Free coverage of BDT 500,000 for death due to accidents, payable to your nominee.

Cancer
Stroke
Myocardial Infarction
Renal Failure
Paralysis
Coronary Artery Surgery
Major Organ Transplant
Blindness
Heart Valve Replacement
Surgery for Diseases of the Aorta
Multiple Sclerosis
Aplastic Anemia
Benign Brain Tumor
End-Stage Lung Disease
Major Head Trauma
Complete Deafness
Loss of Limbs
Loss of Speech

Critical Care Insurance (CCI): The Critical Care Insurance program allows cardmembers to receive benefit of treatment of 18 critical diseases, mentioned above. For Mastercard World Elite Cardmembers , the maximum coverage cardmembers can avail per year under the Critical Care program is BDT 300,000.

### Mastercard Global Offers
Major Offers:

1. One complimentary main course when dining at partner restaurant across Asia Pacific

2. ⁠Private jet and Cruise privileges for the Card Member

3. ⁠Additional advantages for entry in Cannes, Grammy Awards as well as in UEFA champions league.

For full offers: Mastercard World Elite

For Detail Offers:

Concierge Phone number (International): +85230163977

Concierge Email: Mastercard.en-ap@tengroup.com

### Additional Privileges
Flexi Loan & 0% interest FlexiBuy program
Balance Transfer & EMI options
EasyPay
24-hour dedicated customer service
E-Statements
Card Replacement

### Welcome and Annual Gift
Welcome Gift:

Gift 1: Bhawal Resort & Spa, Baywatch Cox’s Bazar, or The Palace Luxury Resort – Sylhet voucher; net worth BDT 13,000 (Choose Any One)

Gift 2: Gadget & Gear or Square Hospital voucher; net worth BDT 10,000 (Choose Any One)

Annual Gift:

Gift 1: Bhawal Resort & Spa, Baywatch – Cox’s Bazar, or The Palace Luxury Resort – Sylhet; net worth BDT 13,000 (All active cardmembers are eligible; Choose Any One)

Gift 2: Gadget & Gear or Mana Bay; net worth BDT 10,000 (Choose Any One)
Eligibility: Cardmember must have BDT 500,000 in yearly transactions to avail Gift 2.

### Fees and Charges
Please click here to download fees and charges

### LoungeKey Access
15 complimentary LoungeKey  Accesses in the international lounges per year. After 15 visits, regular access fee will be charged.  Supplementary cardmember will get complimentary LoungeKey membership  but to get access in the lounge  USD 35 will be charged.

Note: LoungeKey  can only be used at foreign airport lounges and lounge access fee of USD 35 will be applicable.

LoungeKey Website

To explore participating airport lounges and exclusive travel benefits available through your Polygon Bank Polygon Mastercard World Elite Credit Card, please visit: https://www.loungekey.com/citybankplc

You may also create your personal LoungeKey account through this dedicated Website . Simply register using your eligible Polygon Mastercard World Elite Credit Card details and create your User ID and Password. The same credentials can be used to access both the LoungeKey website and the LoungeKey mobile application.

LoungeKey Mobile App

For quick and convenient access to participating airport lounges worldwide, download the LoungeKey app from the Google Play Store or Apple App Store.

### Dining Benefits
From 1 October 2026 to 31 October, 2026, the Buy 1 Get 2 Complimentary Companion Buffet during weekends will be applicable for American Express Platinum Reserve, American Express Platinum and Mastercard World Elite Credit Cardmembers at Crowne Plaza Airport for month of October. Reservation Number: +880 1886 441166, +880 1886 441188

 

Lifestyle Benefits:

Enjoy Buy 1 Get 1 Complimentary Buffet every day at:

The Garden Kitchen, Sheraton Dhaka
Laguna, The Peninsula Chittagong
Attitude, Holiday Inn Dhaka
Café Bazar, Pan Pacific Sonargaon Dhaka
Latest Recipe, Le Méridien Dhaka
Seasonal Tastes, The Westin Dhaka
Amaya, Amari Dhaka
Elements, InterContinental Dhaka
The Flair, Crowne Plaza Dhaka (Gulshan)
Brasserie, Radisson Blu Dhaka Water Garden
The Xchange, Radisson Blu Chattogram Bay View
Rose View Hotel
Crowne Plaza Dhaka Airport
Hyatt Palace Uttara

Source (City Bank page): https://www.citybankplc.com/p/mastercard-world-elite-credit-card

---

## Card 6: PolygonGo

- **City Bank original name:** CityGo
- **Type:** Credit - other
- **Suggestion:** Yes - core (everyday cashback card)

Rediscover Freedom
Welcome to the world of PolygonGo. All new PolygonGo. Live at your own space. Go wherever you want to, move as you wish to, enjoy life as you dream to.
Go wherever you want to, enjoy life as you dream to
2% Cashback on All Spending*
Pay wherever you want and enjoy 2% cashback
Flexibuy at 0% Interest
Buy now pay later with flexibuy at 0% interest
Up to BDT 5,000
Just Tap & Pay and get up to BDT 5,000
International Payment Facilities
Explore the world and pay hassle-free with PolygonGo

### Who are eligible for a PolygonGo?
Customers with a Polygon Bank consumer VISA Credit Card or Current/Savings account are eligible to apply for a PolygonGo.
Note: Foreign Currency cards or Foreign Currency accounts are not eligible.

### What is PolygonGo?
PolygonGo is the latest payment technology chip from Polygon Bank. The PolygonGo chip can be inserted into the Wristband or Strap loop to easily make NFC payments with a tap.

### How can someone apply for a PolygonGo?
Customers can apply for a PolygonGo through our branches, card service centers or sales channel.

### What are the color choices for the Wristbands?
The Wristband can be chosen from three colors; Black, Green and Orange.
Note: Color choices are subject to availability.

### What are the color choices for the Strap loop?
The Strap loop is available in black color only.

### Can the Wristband or Strap loop be purchased separately?
No. The Wristband and Strap loop has to be purchased together. Customer can use either according to his/her convenience

### How to use a PolygonGo?
Customers can start using a PolygonGo by following these simple steps:

Step 1: Remove PolygonGo chip from the chip holder.
Step 2: Activate the PolygonGo chip and generate PIN through Smart IVR/IVR/PolygonTouch Digital Banking.
Step 3: Insert the PolygonGo chip into your Wristband or Strap loop.
Step 4: The PolygonGo device is now ready to make NFC payments.

### What is included in the PolygonGo box?
The box includes:

NFC Wearable Chip
Chip Holder
Wristband
Strap loop
Mailer

### Why use a PolygonGo?
With PolygonGo you can instantly make NFC payments with one tap. Morover, you can wear it on your wrist or pair it with your watch strap. PolygonGo is a blend of convenience and style making your purchases easier with each transaction.

### How to do online transactions with your PolygonGo?
Information provided on the chip holder can be used to make online transactions with the PolygonGo.

### Is there any transaction limit for the PolygonGo?
Maximum 20 NFC transactions can be made per day using your PolygonGo chip.

### Is there any cashback offer on transactions with the PolygonGo?
Yes, 2% cashback upto 1000 per quarter on every PolygonGo POS transaction. Except Fuel station transactions.
Note: Terms & Conditions Applied

### Can a PolygonGo be taken without a card?
PolygonGo (Credit) can only be taken by a VISA Credit Card holder. PolygonGo(Debit) can be taken by a Current/Savings account holder, even without a Debit Card.

### Can new customers apply for a PolygonGo?
Yes. New customers can apply for a PolygonGo along with their application for a new VISA Credit Card or Current/Savings account

### Which Current accounts can be used to take a PolygonGo?
Individual or Proprietorship current accounts can be used to take a PolygonGo.

### Can foreign currency transactions be made with the PolygonGo?
Yes. The PolygonGo chip needs to be endorsed before making transactions in USD or USD equivalent foreign currency.
Note: International POS transactions above BDT 5,000 or USD equivalent cannot be made with the PolygonGo chip, without PIN confirmation.

### What are the allowable modes of usage?
POS, Ecom and Cash By Code.

### What is the validity of the PolygonGo chip?
The PolygonGo chip will have a validity of 5 years. Upon expiry of the chip after 5 years, it will be auto renewed with a re-issue fee. A new set of the product (including Wristband and Strap loop) will be sent to the customer.

### Is there any annual fee for the PolygonGo?
There is no annual fee. Customers will be charged with a one-time issuance fee.

### What to do in case the PolygonGo chip is stolen/lost?
In case of stolen/lost chip, please immediately deactivate the chip through PolygonTouch or by calling 16234. After deactivating the chip, you can request for a replacement through our call center (16234), terms and conditions applied.

### What is the replacement process?
If the chip is stolen/lost/damaged/nonfunctional, it can be replaced by a new set of the product (including Wristband and Strap loop) with a replacement fee. Please call 16234 for replacement request.

### What are the fees and charges for the PolygonGo chip?
The following fees and charges shall be applicable:

| Fee/Charge Type | PolygonGo (Credit) | PolygonGo (Debit) |
|---|---|---|
| Issuance/Re-Issue/Replacement Fee | BDT 3,000 | BDT 3,000 |
| Monthly Interest For Purchase1 | 1.67% | N/A |
| EMI Interest Rate Monthly | 0.92% | N/A |
| Currency Conversion Markup Fee (Other than USD)2 | 3% | 3% |
| Monthly Balance transfer interest rate | 0.92% | N/A |
| Minimum due for monthly payment | BDT 500 or 3% whichever is higher | N/A |
| EMI Early Settlement Fee | 0.5 % of the remaining balance | N/A |
| PIN Regeneration Fee (Call Center Only) | BDT 500 | N/A |
| Fee for Credit Card Payment throughMFS Wallets & Internet Banking Applications3 | BDT 35 | N/A |
| Incoming Fund Transfer3 | N/A | BDT 15 |
| Processing fee for fund transfer from PolygonTouch to CASA and MFS Wallet | BDT 100 or 2% whichever is higher | N/A |
| Fee for Fund Loading to MFS Wallet (Add Money) | 1% | Free |
| ATM cash withdrawal Fee (Cash By Code, for Debit Card Only) | N/A | Free |
| ATM Cash Withdrawal Limit | N/A | As per existing Cash By Code Limit via PolygonTouch |

 

Note

15% VAT shall be charged as applicable.
Compound interest shall be charged on all applicable interest.
Flat interest rate shall be used to calculate the interest payable for EMIs.
Maximum interest free period shall be 45 days and minimum shall be 15 days. Interest shall not be charged if you have paid your previous month’s outstanding amount in due time. If you pay partial amount or minimum amount, the interest on your retail transactions and fees shall be calculated from the following day of your last payment due date.
Interest charges are imposed both on the OUTSTANDING RETAIL TRANSACTION BALANCE & FEES that is not paid within the PAYMENT DUE DATE. Interest shall be calculated from the following day of your last payment due date until full payment.

3% additional markup shall be added at the time of settlement of any international transaction except in USD and shall be reflected on the monthly billing statement.
Note: For PolygonGo (Credit) 3% markup fee is inclusive of VAT.

For credit card bill payment using VISA Direct payment gateway or for incoming fund transfer from all MFS wallets/Internet Banking Applications using VISA Direct payment gateway. Charges will be applicable as per existing process.

### How will the PolygonGo be delivered?
Debit Card PolygonGo taken for a Current/Savings account will be delivered to customer's preferred branch. Customer can then collect it from the branch. Credit Card PolygonGo taken for a VISA Credit Card will be delivered to customer's communication address.

### How to permanently close a PolygonGo?
A PolygonGo can be permanently closed by visiting your nearest Polygon Bank Plc branch.

### Can a PolygonGo be used if the VISA card is closed?
PolygonGo taken for your Current/Savings account can be used even if the VISA Debit Card is closed, provided the account is operational. However, PolygonGo taken for your VISA Credit Card cannot be used if the Credit Card is closed.

Source (City Bank page): https://www.citybankplc.com/p-ca/city-go

---

## Card 7: Polygon Visa Debit Card

- **City Bank original name:** Visa Debit Card
- **Type:** Debit
- **Suggestion:** Yes - core (default debit card)

The Visa Platinum Debit Card from Polygon Bank is now at your service. It reshapes your daily banking with safety and simplicity. The Platinum emblem reflects your elevated lifestyle.
### Features
Dual currency facility
Enjoy hassle-free international ATM, POS and e-com...
Cash withdrawal from VISA-enabled ATMs 24/7/365 al...
Enjoy event-based special savings offers

### Eligibility
If you are an individual and have a savings, current or STD account in Polygon Bank, you are eligible avail this card. Just drop in any nearby Polygon Bank branch, collect an application form and submit duly filled up form. Within shortest time you will get the card delivered at your designated branch.

### Fees and Charges
| Particulars | Amount |
|---|---|
| Annual/Renewal Fee | BDT 700 |
| Card Replacement Fee | BDT 400 |
| Captured Card Replacement Fee | BDT 300 |
| Currency Conversion Markup Fee | 3% on transaction amount |
| Cash Withdrawal Fee | Polygon Bank ATM – Free |
| Cash Withdrawal Fee | Q-Cash ATM – BDT 10 |
| Cash Withdrawal Fee | NPSB ATM- BDT 15 |
| Cash Withdrawal Fee | Foreign ATM- USD 2.75 |
| Cash Withdrawal Fee | Visa Network: BDT 40 (if transaction is routed through other than NPSB or Q-Cash Network) |
| ATM Cash Withdrawal Limit | BDT 40,000 (per transaction) |
| ATM Cash Withdrawal Limit | BDT 100,000 or USD Equivalent (Per Day) |
| Incoming Fund Transfer Fee | BDT 15 |

 

*15% VAT will be charged on applicable cases

**Fund Transfer from all MFS wallets and Internet Banking Applications (Using VISA Direct payment gateway), where applicable

*ATM fee for NPSB Network:

(i) Applicable for first 5 transactions below BDT 20,000 in a month

(ii) NPSB ATM fee of BDT 30 will be charged for 6th transaction onwards in a month or if the amount is above BDT 20,000 in any transaction

### Features
Enjoy hassle free international ATM, POS & E-commerce transaction with your VISA Debit Card
Acceptance at VISA outlets all over the world
Cash withdrawal from VISA enabled ATMs 24/7/365 all over the world
Enjoy event based special savings offer

Source (City Bank page): https://www.citybankplc.com/p/visa-debit-card

---

## Card 8: Polygon Mastercard Debit Card

- **City Bank original name:** Mastercard Debit Card
- **Type:** Debit
- **Suggestion:** Yes - core

Introducing the Polygon Mastercard Debit Card from Polygon Bank. Experience a seamless and secure lifestyle with the convenience of Mastercard, empowering you as a distinguished cardholder.
### Features
Dual currency facility
Acceptance at Mastercard outlets all over the worl...
Cash withdrawal from Mastercard-enabled ATMs 24/7/...
Enjoy event-based special savings offer
Enjoy hassle-free international ATM, POS and e-com...

### Eligibility
Bangladeshi national aged 18 years and above
Having a Savings, Current or STD account with Polygon Bank

### Fees and Charges
| Particulars | Amount |
|---|---|
| Annual/Renewal Fee | BDT 700 |
| Card Replacement Fee | BDT 400 |
| Captured Card Replacement Fee | BDT 300 |
| Currency Conversion Markup Fee | 3% on transaction amount |
| Cash Withdrawal Fee | Polygon Bank ATM – Free |
| Cash Withdrawal Fee | Q-Cash ATM – BDT 10 |
| Cash Withdrawal Fee | NPSB ATM- BDT 15 |
| Cash Withdrawal Fee | Foreign ATM- USD 2.75 |
| Cash Withdrawal Fee | Mastercard Network: BDT 40 (if transaction is routed through other than NPSB or Q-Cash Network) |
| ATM Cash Withdrawal Limit | BDT 40,000 (per transaction) |
| ATM Cash Withdrawal Limit | BDT 100,000 or USD Equivalent (Per Day) |

 

*15% VAT will be charged on applicable cases

*ATM fee for NPSB Network:

Applicable for first 5 transactions below BDT 20,000 in a month
NPSB ATM fee of BDT 30 will be charged for 6th transaction onwards in a month or if the amount is above BDT 20,000 in any transaction

**For details, please contact your nearest  Polygon Bank Branch or Contact Us.

### Features
Enjoy hassle free international ATM, POS & E-commerce transaction with your Card
Acceptance at Mastercard outlets all over the world
Cash withdrawal from Mastercard enabled ATMs 24/7/365 all over the world
Enjoy event based special savings offer

Source (City Bank page): https://www.citybankplc.com/p/mastercard-debit-card

---

## Card 9: Polygon Mastercard Platinum International Debit Card

- **City Bank original name:** Mastercard Platinum International Debit Card
- **Type:** Debit
- **Suggestion:** Yes - core (premium debit)

Experience the power of Platinum. MasterCard Platinum International Debit Card from Polygon Bank is the first dual currency platinum debit card in the country.
International Dual Currency Debit Card available both in Taka and USD
Complimentary Polygon Bank Lounge Access for Primary Cardholders.
### Features
Get access to your funds at over 1.9 million Maste...
Get access to 32 million outlets worldwide that ac...

### Eligibility
Minimum monthly balance of BDT 10 lac or net monthly income of BDT 2 lac and above (salary account to be maintained with Polygon Bank).
For Local Currency Platinum, only BDT account balance will be considered.
For International Platinum (only USD), RFCD/FCY/ERQ account will be considered.
Against each ERQ account maximum 3 cards can be issued.

### Fees and Charges
| Particulars | Amount |
|---|---|
| Annual/Renewal Fee | BDT 1000 |
| Card Replacement Fee | BDT 400 |
| Captured Card Replacement Fee | BDT 300 |
| Currency Conversion Markup Fee | 3% on transaction amount |
| Cash Withdrawal Fee | Polygon Bank ATM – Free |
| Cash Withdrawal Fee | Q-Cash ATM – BDT 10 |
| Cash Withdrawal Fee | NPSB ATM- BDT 15 |
| Cash Withdrawal Fee | Mastercard Network: BDT 40 (if transaction is routed through other than NPSB or Q-Cash Nwtwork) |
| ATM Cash Withdrawal Limit | BDT 40,000 (per transaction) |
| ATM Cash Withdrawal Limit | BDT 100,000 or USD Equivalent (Per Day) |

*15% VAT is applicable for all charges

*ATM fee for NPSB Network:

(i) Applicable for first 5 transactions below BDT 20,000 in a month

(ii) NPSB ATM fee of BDT 30 will be charged for 6th transaction onwards in a month or if the amount is above BDT 20,000 in any transaction

For details, please contact your nearest Polygon Bank Branch or Contact Us.

### Privileges
International Dual Currency Debit card-available both in Taka & USD
Get access to your funds at over 1.9 million Mastercard ATMs world wide
Access to 32 million outlets worldwide that accept Mastercard
Complimentary access for Primary Cardholder with 1 (One) companion to Polygon Bank Lounge at Hazrat Shahjalal International Airport, Dhaka if the minimum annual average balance is USD 2,000 or equivalent. The offer is applicable for MC Platinum debit cards issued against RFCD accounts only

Source (City Bank page): https://www.citybankplc.com/p/mastercard-platinum-international-debit-card

---

## Card 10: Polygon UnionPay Gold Debit Card

- **City Bank original name:** UnionPay Gold Debit Card
- **Type:** Debit
- **Suggestion:** Later - needs scheme membership

Enjoy life your way with Polygon Bank Polygon UnionPay Gold Debit Card. With this card, you can make purchases at numerous POS terminals or online shops worldwide.
### Features
Fast, secure NFC payments
Pay via QR, POS, online
Global 24/7 ATM access
Full PolygonTouch App access
Event-based special savings

### Fees and Charges
| Particulars | Amount |
|---|---|
| Annual/Renewal Fee | BDT 700 |
| Card Replacement Fee | BDT 400 |
| Captured Card Replacement Fee | BDT 300 |
| Currency Conversion Markup Fee | 3% |
| Cash Withdrawal Fee | Polygon Bank ATM – Free |
|  | NPSB Network – BDT 15 |
|  | Foreign ATM – USD 2.75 |
| ATM Cash Withdrawal Limit | BDT 40,000 (per transaction) |
| ATM Cash Withdrawal Limit | BDT 100,000 or USD equivalent (per day) |

 

• ATM fee for NPSB Network:
(i) Applicable for the first 5 transactions below BDT 20,000 per month
(ii) BDT 30 will be charged from the 6th transaction onwards, or for any transaction above BDT 20,000

• 15% VAT is applicable on all charges except NPSB fees

Eligibility:

If you are an individual with a Savings, Current, or STD account at Polygon Bank, you are eligible to avail this card. Visit your nearest Polygon Bank branch, collect the application form, and submit it duly filled. Your card will be delivered to your designated branch within the shortest possible time.

### Features
Enjoy hassle free international ATM, POS & E-commerce transaction with your Card
Acceptance at UnionPay outlets all over the world
Cash withdrawal from UnionPay enabled ATMs 24/7/365 all over the world
Enjoy event based special savings offer

### ATM Cash Withdrawal
Withdraw cash conveniently from your bank account round the clock from all Polygon Bank ATMs in Bangladesh and UnionPay ATMs worldwide.

### 24-hour Customer Service Center
For more information, please call 16234 (locally) and +880 2 8331040 (locally & internationally) or contact the card ambassador at your nearest Polygon Bank branch.

Source (City Bank page): https://www.citybankplc.com/p/unionPay-gold-debit-card

---

## Card 11: Polygon TakaPay Debit Card

- **City Bank original name:** TakaPay Debit Card
- **Type:** Debit
- **Suggestion:** Later - needs scheme membership (Bangladesh local scheme)

Enjoy seamless transactions across the country with Bangladeshs very own card network, ensuring security and national pride in every payment.
### Features
Make faster and safer transactions with NFC-enable...
Pay directly from your account for QR, POS, and on...
Withdraw money 24/7 from Polygon Bank ATMs and other...
Full access to all features of the PolygonTouch App,...
Equipped with a blind notch for easy identificatio...

### Fees and Charges
| Particulars | Amount |
|---|---|
| Annual/Renewal Fee | BDT 700 |
| Card Replacement Fee | BDT 400 |
| Captured Card Replacement Fee | BDT 300 |
| Cash Withdrawal Fee | Polygon Bank ATM – Free, NPSB Network: BDT 15 |
| ATM Cash Withdrawal Limit | BDT 40,000 (per transaction) |
| ATM Cash Withdrawal Limit | BDT 100,000 (Per Day) |

*ATM fee for NPSB Network:

(i) Applicable for first 5 transactions below BDT 20,000 in a month

(ii) NPSB ATM fee of BDT 30 will be charged for 6th transaction onwards in a month or if the amount is above BDT 20,000 in any transaction

(iii) Monthly NPSB ATM cash withdrawal limit is BDT 200,000

*15% VAT is applicable for all charges except NPSB fee

Source (City Bank page): https://www.citybankplc.com/p/takaPay-debit-card

---

## Card 12: Polygon Digital Visa Platinum Debit Card

- **City Bank original name:** City Alo Visa Platinum Debit Card
- **Type:** Debit
- **Suggestion:** Only if Polygon has a digital-account brand

Polygon Digital Visa Platinum Debit Card is bundled with exciting benefits and features. Enjoy cashback facilities and receive welcome vouchers with discounts from renowned merchants. Also receive round the year privilege offers from various outlets all across the country.

### Fees and Charges
| Particulars | Fees |
|---|---|
| Annual Fee | BDT 700 |
| Card Replacement Fee Captured Card Replacement Fee | BDT 400 BDT 300 |
| Currency Conversion Markup Fee | 3% on transaction amount |
| Cash Withdrawal Fee | Polygon Bank ATM – Free |
| Cash Withdrawal Fee | Q-Cash ATM – BDT 10 |
| Cash Withdrawal Fee | NPSB ATM - BDT 15 |
| Cash Withdrawal Fee | Foreign ATM – USD 2.75 |
| ATM Cash Withdrawal Limit | BDT 20,000 (per transaction) |
| ATM Cash Withdrawal Limit | BDT 1,00,000 or USD Equivalent (per day) |

 

*15% VAT will be charged on applicable cases

**Fund Transfer from all MFS wallets and Internet Banking Applications (Using VISA Direct payment gateway), where applicable

*ATM fee for NPSB Network:

(i) Applicable for first 5 transactions below BDT 20,000 in a month

(ii) NPSB ATM fee of BDT 30 will be charged for 6th transaction onwards in a month or if the amount is above BDT 20,000 in any transaction

### Welcome Vouchers
You will receive exclusive welcome vouchers with Polygon Digital VISA Debit Card:

Woman’s World : Enjoy 20% discount on all services and 10% discount on all products.
Smartex : Enjoy 10% discount on all goods.
Artisan Outfitters Ltd : Enjoy 15% discount on everything apart from leather goods.

### Exclusive Design
Add more beauty to your wallet with your hands on our attractive Polygon Digital VISA Debit Card.

### Cashback
Enjoy 1% cashback on clothing, dining, groceries, hospitals and medicine stores.

Terms & Conditions: 

Cashback is applicable for transactions made through Polygon Bank’s POS terminals at merchant outlets.
The cashback is not applicable for ATM transactions and USD transactions.
Accumulated cashback amount will be credited to your account at the end of each quarter.
Maximum BDT 1000 cashback amount can be earned per month .

*Terms and conditions applied.

### Dual Card Facility
Enjoy hassle free international ATM, POS & E-commerce transaction with your Polygon Digital VISA Debit Card.

### Discount Offers
Enjoy discount offers round the year while you spend with your Polygon Digital Debit Card at various merchant outlets.

To view our beauty salon partners, Click Here. 

To view our dining partners, Click Here.

To view our healthcare partners, Click Here.

Source (City Bank page): https://www.citybankplc.com/p/city-alo-visa-platinum-debit-card

---

