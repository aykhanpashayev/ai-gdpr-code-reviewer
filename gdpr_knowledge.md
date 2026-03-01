# GDPR Developer Knowledge Base  
## Practical GDPR Principles for Secure Software Development  

This document summarizes key GDPR principles relevant to developers and software systems.  
It is intended for compliance-aware code review and educational use.  

**This is not legal advice.**

---

# 1. What is Personal Data?

Personal data is any information that can directly or indirectly identify a natural person.

### Examples

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

If code processes any of the above (storage, logging, transmission, analytics), GDPR may apply.

---

# 2. Core GDPR Principles (Article 5)

## 2.1 Lawfulness, Fairness, Transparency

Personal data must be:

- Processed lawfully  
- Used fairly  
- Clearly explained to users  

### Developer Considerations

- Is there a documented legal basis in system design?
- Is user consent required and properly handled?
- Is data usage clearly defined in product requirements?

**Red flag:**  
Collecting data without defined purpose or legal basis.

---

## 2.2 Purpose Limitation

Data must be collected for specific, explicit, legitimate purposes.

### Developer Considerations

- Is the purpose defined in the system?
- Is data reused for unrelated features?
- Is logging collecting extra information beyond original purpose?

**Red flag:**  
Using collected emails for unrelated marketing without consent.

---

## 2.3 Data Minimization

Only collect data that is necessary.

### Developer Considerations

- Are unnecessary fields collected?
- Is excessive logging storing PII?
- Are entire objects stored when only a single field is required?

**Red flag:**  
Storing full user profiles when only an email is required.

---

## 2.4 Accuracy

Personal data must be accurate and up to date.

### Developer Considerations

- Can users update their information?
- Are validation checks implemented?
- Are outdated records cleaned?

**Red flag:**  
No mechanism to correct incorrect user data.

---

## 2.5 Storage Limitation

Data must not be stored longer than necessary.

### Developer Considerations

- Is there a defined retention policy?
- Are logs rotated and deleted?
- Are old records archived or purged?

**Red flag:**  
Indefinite database retention of user records without justification.

> Storage duration must be appropriate to the purpose and risk.  
> Temporary in-memory storage for demos may not represent production compliance risk.

---

## 2.6 Integrity and Confidentiality (Security Principle)

Personal data must be protected using appropriate technical and organizational measures.

Security measures must be **appropriate to the risk and sensitivity** of the data processed.

### Developer Considerations

- Is encryption used (HTTPS/TLS for data in transit)?
- Is encryption at rest used where appropriate?
- Are passwords hashed securely (bcrypt, argon2)?
- Are secrets hardcoded?
- Are access controls enforced?
- Is authentication required before data access?

### Red Flags

- Plaintext passwords  
- Hardcoded API keys  
- Unencrypted HTTP  
- Logging sensitive information  
- No authentication checks before returning user data  

---

## 2.7 Accountability

Organizations must demonstrate compliance.

### Developer Considerations

- Are actions logged securely (without exposing PII)?
- Are access attempts auditable?
- Is system behavior traceable?

**Red flag:**  
No traceability of data access or modification.

> Logging must avoid storing unnecessary personal data.

---

# 3. Lawful Bases for Processing (Article 6)

Processing must rely on at least one lawful basis:

- Consent  
- Contract necessity  
- Legal obligation  
- Vital interests  
- Public task  
- Legitimate interest  

### Developer Consideration

If the system collects personal data, the legal basis should be documented in system design, policies, or product documentation.

**Red flag:**  
Processing personal data with no identifiable lawful basis.

---

# 4. Security of Processing (Article 32)

Organizations must implement appropriate technical and organizational measures.

### Recommended Security Practices

- HTTPS (TLS encryption in transit)  
- Encryption at rest where appropriate  
- Role-based access control (RBAC)  
- Multi-factor authentication (MFA)  
- Secure password hashing (bcrypt, argon2)  
- Input validation and sanitization  
- Regular security testing  

### Red Flags

- Unencrypted HTTP  
- No authentication before data retrieval  
- Direct SQL queries without validation  
- Sensitive data stored in logs  
- Public cloud storage buckets  

> Security requirements are risk-based.  
> Controls must be proportionate to data sensitivity and system exposure.

---

# 5. Data Subject Rights (Developer-Relevant)

Systems must allow support for:

- Right of access  
- Right to rectification  
- Right to erasure  
- Right to restrict processing  
- Right to data portability  
- Right to object  

### Developer Considerations

- Is there a deletion function?
- Can user data be exported?
- Can data be corrected?
- Is identity verified before granting access?
- Are access control checks implemented?

> Absence of a direct API endpoint does **NOT automatically mean non-compliance.**  
> Rights may be fulfilled through organizational or manual processes.  
> However, production systems should support structured and secure mechanisms.

**Red flag:**  
Returning personal data without authentication or authorization.

---

# 6. Privacy by Design and by Default (Article 25)

Systems must be designed with privacy built in.

### Developer Considerations

- Default settings collect minimal data.
- Privacy does not rely on user configuration.
- Access is restricted by default.
- Debug mode does not expose personal data.

**Red flag:**  
System exposes user data publicly unless manually restricted.

---

# 7. High-Risk Technical Patterns

The following patterns often indicate GDPR risk:

- Hardcoded credentials  
- Logging personal data  
- Storing passwords in plaintext  
- Using HTTP instead of HTTPS  
- Excessive data retention  
- Sharing data with third parties without safeguards  
- No access control on admin routes  
- Public cloud storage buckets  
- No authentication before returning user data  
- No audit trace of sensitive operations  

---

# 8. AI Compliance Reviewer Instructions

When reviewing code:

1. Identify whether personal data is processed.
2. Map code behavior to relevant GDPR principles.
3. Provide evidence-based findings (reference functions, variables, routes).
4. Classify severity (High / Medium / Low).
5. Suggest realistic technical remediation.
6. If context is insufficient, explicitly state **"Insufficient context"**.
7. Do NOT automatically label systems as “non-compliant.”
8. Do NOT invent legal interpretations beyond provided information.

The reviewer must remain technical and avoid legal conclusions.

---

# 9. Limitations

This knowledge base provides simplified technical interpretations of GDPR for educational purposes.

It does not replace:

- Legal counsel  
- Certified compliance audits  
- Official regulatory interpretation  

GDPR compliance depends on:

- Code  
- Infrastructure  
- Organizational processes  
- Documentation  
- Risk assessment  

Always consult a qualified data protection professional for legal compliance validation.