# QA cases: citations-confidence

Hits below are written as (url, retrieval, rerank). Threshold means min_confidence.

### QA-001 Valid citations give an answer
- Covers: Scenario 1 (valid citations), Metric 1
- Type: functional
- Given threshold 0.5 and two hits: (https://eli.gov.pl/akt/1, 0.8, none) and (https://eli.gov.pl/akt/2, 0.6, none)
- When the caller asks for a decision
- Then the result is an answer with 2 citations, each with an https source link and confidence 0.8 and 0.6, answer confidence 0.8

### QA-002 Below threshold gives refusal
- Covers: Scenario 2 (below threshold), Business Goals
- Type: functional
- Given threshold 0.5 and one hit (https://eli.gov.pl/akt/1, 0.3, none)
- When the caller asks for a decision
- Then the result is "no reliable answer" with closest source https://eli.gov.pl/akt/1 and no confidence value

### QA-003 No citation gives refusal
- Covers: Scenario 3 (no citation), Edge Case all hits lack valid citation
- Type: functional
- Given threshold 0.5 and one hit with an empty source URL and retrieval score 0.9
- When the caller asks for a decision
- Then the result is "no reliable answer" with 0 closest sources

### QA-004 Setting changes outcome
- Covers: Scenario 4 (setting changes outcome), Edge Case 0.4 with 0.3
- Type: functional
- Given one hit (https://eli.gov.pl/akt/1, 0.4, none)
- When the caller decides with threshold 0.3, then again with threshold 0.5
- Then the first result is an answer with confidence 0.4 and the second is "no reliable answer"

### QA-005 Shared notice text
- Covers: Scenario 5 (shared notice), Failure Mode notice never empty
- Type: functional
- Given the shared notice text and one answer result and one refusal result
- When the caller reads the notice of each result
- Then both notices are equal to the shared text, which is not empty and holds "not legal advice" in any letter case

### QA-006 ADR-0008 accepted
- Covers: Scenario 6 (ADR accepted), Technical Constraints ADR change
- Type: functional
- Given the ADR-0008 document and the ADR index
- When a reader looks at the status of ADR-0008
- Then the front matter and the index row both say accepted, and the text says Citation is a value object with persistence deferred and weights 0.4 and 0.6 provisional

### QA-007 Empty hit list
- Covers: Edge Case empty hit list
- Type: edge
- Given threshold 0.5 and an empty hit list
- When the caller asks for a decision
- Then the result is "no reliable answer" with 0 closest sources

### QA-008 Confidence equal to threshold
- Covers: Edge Case equal to threshold, Metric 3
- Type: edge
- Given threshold 0.5 and one hit (https://eli.gov.pl/akt/1, 0.5, none)
- When the caller asks for a decision
- Then the result is an answer with confidence 0.5

### QA-009 Confidence just below threshold
- Covers: Metric 3
- Type: edge
- Given threshold 0.5 and one hit (https://eli.gov.pl/akt/1, 0.49, none)
- When the caller asks for a decision
- Then the result is "no reliable answer"

### QA-010 Confidence 0.4 with threshold 0.3
- Covers: Metric 3, Edge Case 0.4 with 0.3
- Type: edge
- Given threshold 0.3 and one hit (https://eli.gov.pl/akt/1, 0.4, none)
- When the caller asks for a decision
- Then the result is an answer with confidence 0.4

### QA-011 Confidence 0.4 with threshold 0.5
- Covers: Edge Case 0.4 with 0.5
- Type: edge
- Given threshold 0.5 and one hit (https://eli.gov.pl/akt/1, 0.4, none)
- When the caller asks for a decision
- Then the result is "no reliable answer"

### QA-012 Retrieval score above 1
- Covers: Edge Case score outside [0, 1], Failure Mode ValueError
- Type: failure
- Given threshold 0.5 and one hit with retrieval score 1.2
- When the caller asks for a decision
- Then the call fails with a ValueError that names the retrieval score field, and no answer is returned

### QA-013 Negative retrieval score
- Covers: Edge Case score outside [0, 1]
- Type: failure
- Given threshold 0.5 and one hit with retrieval score -0.1
- When the caller asks for a decision
- Then the call fails with a ValueError that names the retrieval score field

### QA-014 Rerank score above 1
- Covers: Edge Case score outside [0, 1]
- Type: failure
- Given threshold 0.5 and one hit with retrieval 0.7 and rerank score 1.5
- When the caller asks for a decision
- Then the call fails with a ValueError that names the rerank score field

### QA-015 NaN score
- Covers: Edge Case NaN
- Type: failure
- Given threshold 0.5 and one hit with retrieval score NaN
- When the caller asks for a decision
- Then the call fails with a ValueError that names the retrieval score field

### QA-016 Infinite score
- Covers: Edge Case infinity
- Type: failure
- Given threshold 0.5 and one hit with rerank score +infinity and retrieval 0.7
- When the caller asks for a decision
- Then the call fails with a ValueError that names the rerank score field

### QA-017 Bool score
- Covers: Edge Case bool
- Type: failure
- Given threshold 0.5 and one hit with retrieval score True
- When the caller asks for a decision
- Then the call fails with a ValueError that names the retrieval score field, and True is not read as 1.0

### QA-018 Text score
- Covers: Edge Case not a number
- Type: failure
- Given threshold 0.5 and one hit with retrieval score "0.9" as text
- When the caller asks for a decision
- Then the call fails with a ValueError that names the retrieval score field

### QA-019 Threshold above 1
- Covers: Edge Case min_confidence outside [0, 1]
- Type: failure
- Given one valid hit (https://eli.gov.pl/akt/1, 0.9, none) and threshold 1.1
- When the caller asks for a decision
- Then the call fails with a ValueError that names the threshold

### QA-020 Negative threshold
- Covers: Edge Case min_confidence outside [0, 1]
- Type: failure
- Given one valid hit and threshold -0.2
- When the caller asks for a decision
- Then the call fails with a ValueError that names the threshold

### QA-021 Threshold at the range limits
- Covers: Edge Case min_confidence range
- Type: edge
- Given one hit (https://eli.gov.pl/akt/1, 0.0, none)
- When the caller decides with threshold 0.0, then with threshold 1.0
- Then the first result is an answer with confidence 0.0 and the second is "no reliable answer"

### QA-022 Empty URL dropped
- Covers: Edge Case empty URL
- Type: edge
- Given threshold 0.5 and hits (empty URL, 0.9, none) and (https://eli.gov.pl/akt/2, 0.6, none)
- When the caller asks for a decision
- Then the answer holds 1 citation with https://eli.gov.pl/akt/2

### QA-023 Non-http URL dropped
- Covers: Edge Case URL not http or https
- Type: edge
- Given threshold 0.5 and hits (ftp://files.gov.pl/a, 0.9, none), (javascript:alert(1), 0.9, none) and (file:///etc/passwd, 0.9, none)
- When the caller asks for a decision
- Then the result is "no reliable answer" with 0 closest sources

### QA-024 URL with credentials dropped
- Covers: Edge Case URL holding credentials, Failure Mode
- Type: security
- Given threshold 0.5 and one hit (https://admin:secret@eli.gov.pl/akt/1, 0.9, none)
- When the caller asks for a decision
- Then the result is "no reliable answer" and no result field holds the text "secret"

### QA-025 Plain http URL kept
- Covers: Edge Case URL http or https
- Type: edge
- Given threshold 0.5 and one hit (http://eli.gov.pl/akt/1, 0.8, none)
- When the caller asks for a decision
- Then the answer holds 1 citation with that http link

### QA-026 No rerank score uses retrieval score
- Covers: Edge Case hit with no rerank score
- Type: functional
- Given threshold 0.5 and one hit (https://eli.gov.pl/akt/1, 0.72, none)
- When the caller asks for a decision
- Then the citation confidence is 0.72

### QA-027 Both scores are weighted
- Covers: Technical Constraints scoring rule, Decision rule
- Type: functional
- Given threshold 0.5 and one hit (https://eli.gov.pl/akt/1, 0.5, 0.9)
- When the caller asks for a decision
- Then the citation confidence is 0.74 (0.4 times 0.5 plus 0.6 times 0.9)

### QA-028 Weights sum to one
- Covers: Decision rule, Metric 6 (OPEN: weights provisional)
- Type: functional
- Given the retrieval weight 0.4 and the rerank weight 0.6
- When the weights are added
- Then the sum is exactly 1.0 and a hit with both scores at 1.0 has confidence 1.0

### QA-029 Rerank lowers a high retrieval score
- Covers: Decision rule, Failure Mode no score above threshold as fact
- Type: functional
- Given threshold 0.5 and one hit (https://eli.gov.pl/akt/1, 0.9, 0.1)
- When the caller asks for a decision
- Then the confidence is 0.42 and the result is "no reliable answer" with that source listed

### QA-030 Answer sorted by confidence
- Covers: Decision Answer.citations order, Metric 1
- Type: functional
- Given threshold 0.5 and hits A (https://eli.gov.pl/a, 0.6, none), B (https://eli.gov.pl/b, 0.9, none), C (https://eli.gov.pl/c, 0.7, none)
- When the caller asks for a decision
- Then citations are B, C, A and the answer confidence is 0.9

### QA-031 Tie keeps input order
- Covers: Edge Case tie keeps input order
- Type: edge
- Given threshold 0.5 and hits A (https://eli.gov.pl/a, 0.8, none), B (https://eli.gov.pl/b, 0.8, none), C (https://eli.gov.pl/c, 0.8, none)
- When the caller asks for a decision
- Then citations come in the order A, B, C

### QA-032 Answer drops hits below threshold
- Covers: Decision Answer.citations filter
- Type: functional
- Given threshold 0.5 and hits (https://eli.gov.pl/a, 0.9, none) and (https://eli.gov.pl/b, 0.2, none)
- When the caller asks for a decision
- Then the answer holds only the citation for https://eli.gov.pl/a

### QA-033 Closest sources limited to 3
- Covers: Edge Case closest sources at most 3
- Type: edge
- Given threshold 0.9 and 5 valid hits with scores 0.1, 0.4, 0.3, 0.2, 0.5
- When the caller asks for a decision
- Then the result is "no reliable answer" with 3 closest sources, scores 0.5, 0.4, 0.3 in that order

### QA-034 Closest sources tie order
- Covers: Edge Case closest sources tie
- Type: edge
- Given threshold 0.9 and 4 valid hits A, B, C, D all with retrieval score 0.3
- When the caller asks for a decision
- Then closest sources are A, B, C in input order

### QA-035 Refusal has no answer fields
- Covers: Failure Mode union, caller cannot read an answer from a refusal
- Type: failure
- Given a "no reliable answer" result
- When a caller reads its citations or its confidence
- Then the read fails because the refusal has no such fields, and only closest sources and the notice are present

### QA-036 Invalid hit after a valid hit still checked
- Covers: Failure Mode bad input never silent, Types and order note
- Type: failure
- Given threshold 0.5 and hits (empty URL, 1.7, none) and (https://eli.gov.pl/a, 0.9, none)
- When the caller asks for a decision
- Then the call fails with a ValueError that names the retrieval score field, and the bad hit is not dropped silently

### QA-037 Invalid hit placed last still checked
- Covers: Failure Mode bad input never silent
- Type: failure
- Given threshold 0.5 and hits (https://eli.gov.pl/a, 0.9, none) and (https://eli.gov.pl/b, NaN, none)
- When the caller asks for a decision
- Then the call fails with a ValueError and no answer is returned

### QA-038 Repeated call gives same result
- Covers: Technical Constraints deterministic rule
- Type: functional
- Given threshold 0.5 and hits (https://eli.gov.pl/a, 0.6, 0.8) and (https://eli.gov.pl/b, 0.7, none)
- When the caller decides 100 times with the same input
- Then all 100 results are equal

### QA-039 Input list not changed
- Covers: Technical Constraints pure module
- Type: edge
- Given a list of 3 hits in the order 0.5, 0.9, 0.7 and threshold 0.5
- When the caller asks for a decision
- Then the input list still has the order 0.5, 0.9, 0.7

### QA-040 Optional fields kept
- Covers: Decision Citation fields
- Type: functional
- Given threshold 0.5 and one hit with law "Kodeks rodzinny i opiekunczy", article "135", paragraph "1", quote "Zakres obowiazku alimentacyjnego...", score 0.8
- When the caller asks for a decision
- Then the citation shows the same law, article, paragraph, quote and link

### QA-041 Missing optional fields
- Covers: Decision Citation optional fields
- Type: edge
- Given threshold 0.5 and one hit with only a link, quote and score 0.8
- When the caller asks for a decision
- Then the answer is returned and the law, article and paragraph are empty

### QA-042 Citation values cannot change
- Covers: Technical Constraints frozen value objects
- Type: failure
- Given an answer with one citation of confidence 0.8
- When a caller sets the confidence to 0.99
- Then the change is refused and the confidence stays 0.8

### QA-043 No I/O packages imported
- Covers: Metric 4, Technical Constraints no LLM, HTTP or DB
- Type: security
- Given the two new modules
- When the import test lists their imports
- Then none is a database, HTTP, Redis, Celery or LLM package, and only the standard library and the notice module are present

### QA-044 Threshold not read from environment
- Covers: Technical Constraints module does not read environment
- Type: edge
- Given the setting for minimum confidence is 0.1 in the environment and one hit scored 0.3 with caller threshold 0.5
- When the caller asks for a decision
- Then the result is "no reliable answer" because the passed threshold of 0.5 is used

### QA-045 Quality gate
- Covers: Metric 5
- Type: performance
- Given the two new modules and their unit tests
- When the lint, format check, type check and tests run with coverage
- Then all four pass and line coverage of both modules is 100 percent

### QA-046 Large hit list
- Covers: Business Goals budget 4-6 GB RAM, no model
- Type: performance
- Given threshold 0.5 and 10000 valid hits with distinct links and scores
- When the caller asks for a decision
- Then the result returns in under 1 second with citations sorted by confidence and no model load

### QA-047 Four or more hit sets pass validity
- Covers: Metric 1
- Type: functional
- Given 4 hit sets: all high, all low, mixed with invalid links, and mixed with rerank scores, threshold 0.5
- When the caller decides on each set
- Then every citation in every result has a valid http or https link and confidence from 0.0 to 1.0

### QA-048 Weights provisional
- Covers: Metric 6
- Type: functional
- Given the ADR-0008 text
- When a reader looks for the scoring rule
- Then the rule and weights 0.4 and 0.6 are stated as provisional until an evaluation runs. OPEN: the weight between retrieval and rerank score cannot be tuned before the search service and an evaluation exist

### QA-049 Notice present on both results
- Covers: Failure Mode user sees refusal and sources
- Type: failure
- Given threshold 0.5 and a hit scored 0.2
- When the caller asks for a decision
- Then the user-visible result holds the notice, the closest source link, and no score shown as an answer
