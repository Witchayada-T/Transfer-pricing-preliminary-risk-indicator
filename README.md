# Transfer Pricing Preliminary Risk Indicator

A preliminary review aid for considering a company’s financial position and business context. **Machine learning is used only to identify unusual financial patterns. It does not determine whether transfer pricing is incorrect.**

[Download Windows application](https://github.com/Witchayada-T/Transfer-pricing-preliminary-risk-indicator/releases/download/standalone-v1.2/TransferPricingReviewer.exe) · [Application with guide (ZIP)](https://github.com/Witchayada-T/Transfer-pricing-preliminary-risk-indicator/releases/download/standalone-v1.2/TransferPricingReviewer_Windows.zip) · [General project overview](GENERAL_OVERVIEW.html) · [User guide](docs/USER_GUIDE.md) · [Sharing and confidentiality](docs/SHARING.md)

## Purpose

The tool supports a reviewer in identifying matters that may deserve closer attention. A financial pattern can be unusual and still have a valid, documented commercial explanation. The assessment depends on the company’s functions, assets, risks, transactions and relevant law.

## What is available here

- A general HTML overview.
- A guide explaining how an authorised reviewer uses the local standalone application.
- A compiled Windows 64-bit application; no Python installation is required.
- Background links to OECD guidance and Thai Revenue Department materials.

Separate source code, trained-model files, numerical decision-rule documents, company observations and original evidence archives are **not offered in this public-facing edition**. The executable contains the resources it needs to run offline; compilation does not guarantee protection against inspection or reverse engineering.

## Run locally

Download `TransferPricingReviewer.exe` and open it on Windows. If using the ZIP, extract it first. Keep the small controller window open while using the application in the browser. Closing the controller stops the local server. Startup can take a little time while the executable unpacks its runtime. The app does not retrain or collect company data. If the download or unsigned executable is blocked by an organisation's policy, ask its IT administrator about an approved distribution route.

The compiled release passed Windows checks for interface rendering, an independent company-context review, supported financial inference, unsupported-industry handling, server health and controller shutdown. These are software smoke checks, not validation of tax outcomes.

## Read the legal and professional background

- [OECD Transfer Pricing Guidelines (2022)](https://www.oecd.org/en/publications/oecd-transfer-pricing-guidelines-for-multinational-enterprises-and-tax-administrations-2022_0e655865-en.html).
- [Thai Revenue Department — official English website](https://www.rd.go.th/english/index-eng.html), for applicable Thai legislation and guidance.

These sources provide transfer-pricing background. They do not disclose the software’s confidential implementation, and the tool does not replace the applicable law or professional judgement.

## How to interpret a result

An unusual financial pattern or a preliminary concern is a reason to review information, not an allegation of non-compliance. Missing information is not a pass. Commercial explanations should be supported by evidence and assessed in context. The study covers a limited set of industries and available observations; its outputs can change if suitable data are added and the models are recalibrated.
