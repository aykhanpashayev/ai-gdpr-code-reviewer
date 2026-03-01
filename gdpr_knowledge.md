# GDPR Developer Knowledge Base
## Practical GDPR Principles for Secure Software Development

This document summarizes key GDPR principles relevant to developers and software systems.  
It is intended for compliance-aware code review and educational use.

This is not legal advice.

---

# 1. What is Personal Data?

Personal data is any information that can directly or indirectly identify a person.

Examples:
- Name
- Email address
- Phone number
- IP address
- Device identifiers
- Location data
- User IDs linked to individuals
- Biometric data
- Financial information
- Health data

If code processes any of the above, GDPR applies.

---

# 2. Core GDPR Principles (Article 5)

## 2.1 Lawfulness, Fairness, Transparency

Personal data must be:
- Processed lawfully
- Used fairly
- Clearly explained to users

Developer considerations:
- Is there a documented legal basis?
- Is user consent required?
- Is data usage clearly defined?

Red flag:
- Collecting data without explaining why.

---

## 2.2 Purpose Limitation

Data must be collected for specific, explicit, legitimate purposes.

Developer considerations:
- Is the purpose defined in the system?
- Is data reused for unrelated purposes?
- Is logging collecting extra information beyond the original purpose?

Red flag:
- Using collected emails for unrelated marketing without consent.

---

## 2.3 Data Minimization

Only collect data that is necessary.

Developer considerations:
- Are unnecessary fields collected?
- Is excessive logging storing PII?
- Are full objects stored when only partial data is needed?

Red flag:
- Storing full user profiles when only an email is required.

---

## 2.4 Accuracy

Personal data must be accurate and up to date.

Developer considerations:
- Can users update their information?
- Are validation checks implemented?
- Are outdated records cleaned?

Red flag:
- No mechanism to correct incorrect user data.

---

## 2.5 Storage Limitation

Data must not be stored longer than necessary.

Developer considerations:
- Is there a retention policy?
- Are old logs deleted?
- Is archival controlled?

Red flag:
- Indefinite database retention of user records.

---

## 2.6 Integrity and Confidentiality (Security Principle)

Personal data must be protected using appropriate security measures.

Developer considerations:
- Is encryption used (in transit and at rest)?
- Are passwords hashed securely?
- Are access controls enforced?
- Are secrets hardcoded?

Red flags:
- Plaintext passwords
- Hardcoded API keys
- Public database access
- Logging sensitive information

---

## 2.7 Accountability

Organizations must demonstrate compliance.

Developer considerations:
- Are actions logged securely?
- Are access controls auditable?
- Is security documentation maintained?

Red flag:
- No traceability of data access.

---

# 3. Lawful Bases for Processing (Article 6)

Processing must rely on at least one lawful basis:

- Consent
- Contract necessity
- Legal obligation
- Vital interests
- Public task
- Legitimate interest

Developer consideration:
If the system collects personal data, the legal basis must be documented somewhere in the system design.

Red flag:
Processing personal data with no identifiable legal basis.

---

# 4. Security of Processing (Article 32)

Organizations must implement appropriate technical and organizational measures.

Recommended security practices:

- Encryption (TLS for data in transit)
- Database encryption at rest
- Role-based access control (RBAC)
- Multi-factor authentication
- Secure password hashing (bcrypt, argon2)
- Regular vulnerability testing
- Input validation and sanitization

Red flags:
- Unencrypted HTTP
- No authentication checks
- Direct SQL queries without validation
- Sensitive data stored in logs

---

# 5. Data Subject Rights (Developer-Relevant)

Systems must allow:

- Right of access (user can request their data)
- Right to rectification (correct data)
- Right to erasure (delete account/data)
- Right to restrict processing
- Right to data portability
- Right to object to processing

Developer considerations:
- Is there an account deletion function?
- Can user data be exported?
- Can personal data be fully removed?

Red flag:
No way for users to delete their account or data.

---

# 6. Privacy by Design and by Default (Article 25)

Systems must be designed with privacy built in.

Developer considerations:
- Default settings should collect minimal data.
- Privacy should not rely on user configuration.
- Access should be restricted by default.

Red flag:
System exposes user data publicly unless manually restricted.

---

# 7. High-Risk Technical Patterns

The following patterns often violate GDPR principles:

- Hardcoded credentials
- Logging personal data
- Storing passwords in plaintext
- Using HTTP instead of HTTPS
- Excessive data retention
- Sharing data with third parties without safeguards
- No access control on admin routes
- Public cloud storage buckets
- No audit logging

---

# 8. AI Compliance Reviewer Instructions

When reviewing code:

1. Identify whether personal data is processed.
2. Map code behavior to relevant GDPR principles.
3. Provide evidence-based findings.
4. Classify severity (High / Medium / Low).
5. Suggest technical remediation.
6. If context is insufficient, state "Insufficient context".

The reviewer must not invent legal conclusions beyond provided information.

---

# 9. Limitations

This knowledge base provides simplified technical interpretations of GDPR for educational purposes.

It does not replace:
- Legal counsel
- Certified compliance audits
- Official regulatory interpretation

Always consult a qualified data protection professional for legal compliance validation.