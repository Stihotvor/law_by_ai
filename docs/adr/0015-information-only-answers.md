---
status: proposed
---

# ADR-0015: Answers are legal information, not legal advice

## Context

The platform answers legal questions for citizens and expats in Poland. The
charter sets one boundary: the system does not bypass or trick the law. The
charter also describes the product as an "AI lawyer". That wording suggests
that the system gives advice and takes responsibility for the result.

A language model can produce fluent answers that are wrong or out of date. A
user may act on such an answer. The product needs an explicit output contract
that states what the system is, what it must not do, and how it shows the
limits of its answers.

## Decision

1. **Answers are information only.** The system explains laws, procedures, and
   documents. It does not give legal advice, and it does not replace a
   qualified lawyer. The user decides and acts.
2. **Every answer shows a notice.** The notice states that the answer is
   information, may be incomplete or outdated, and is not legal advice. The UI
   shows it next to each answer from the research, analysis, and bureaucracy
   features.
3. **Every answer rests on sources.** An answer includes the citations,
   confidence scores, and source links defined in ADR-0008. If the confidence
   is below the set threshold, or no citation supports the answer, the user
   sees "no reliable answer" and the closest sources. The threshold is a
   setting. An evaluation tunes it.
4. **The system does not help to bypass the law.** It refuses requests to
   evade, hide from, or trick a legal obligation or authority. The
   bureaucracy assistant guides only lawful procedures.
5. **A person stays in the loop.** The assistant produces drafts of forms and
   letters. The user reviews them and submits them. The system never submits
   anything for the user. This follows the human-in-the-loop model of the
   agents.
6. **Product wording matches the contract.** The charter, the documents, and the
   UI do not present the system as a lawyer or as a replacement for one.

## Consequences

- Clear expectations for users and clear limits for the model output.
- The notice and the refusal rule need prompt design, UI work, and tests.
  Tests include requests that try to bypass the law and queries with no
  supporting source.
- Some questions get a "no reliable answer" reply with the closest sources
  instead of a fluent guess. This lowers the apparent coverage and raises
  trust.
- The charter pitch ("AI lawyer") must change to match item 6.
- This ADR does not give legal certainty. The owner may need a legal review of
  the notice text before release.

## Alternatives Considered

- **Position the product as legal advice** - needs lawyer supervision and
  liability cover. It is out of reach for an open-source project run by one
  person.
- **No explicit contract** - leaves the limits to each prompt and each page.
  The behavior drifts and cannot be tested.
- **Answer from model memory when confidence is low** - raises coverage but
  produces unsupported legal claims.

## Related

- [ADR-0008](0008-mvp-scope.md) - citations, confidence, source links
- [ADR-0003](0003-multi-tenancy.md) - isolation of user data
- [Intention](../intention.md) #1, #6, #15, #32, #37, #41
- [Architecture](../architecture.md) - Agents Layer
