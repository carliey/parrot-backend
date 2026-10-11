# Beginner Hausa lesson plans

Version: `practice-3`. Vocabulary, English glosses, and cultural guidance follow the project owner's notes of 11 October 2026. They remain marked as draft content awaiting language review. No new pronunciation guides have been invented.

## Editing content

The source is `app/lesson_plans.json`. Each lesson contains vocabulary cards, cultural notes, roles, and ordered steps. A step defines expected learner utterances, a hint, and permitted tutor replies. The `name` matcher permits a short name after `Suna na` / `Sunana`.

After editing, run `python3 sync_lessons.py` from this backend directory to update the mobile bundle. Run `python3 sync_lessons.py --check` to verify parity. Increment the version when changing practice rules. Existing sessions retain their recorded version and require a new session after a curriculum update.

## 1. Greetings

The learner plays the elder; the tutor is the younger person. Do not have the child address an elder with `Ya kake?` / `Ya kike?`.

| Step | Learner | Tutor may reply |
| --- | --- | --- |
| Greet | Sannu | Yauwa |
| Time of day | Ina kwana? / Barka da safiya / Ina yini? / An yini lafiya? | Lafiya / Lafiya lau |
| Wellbeing | Ya kake? / Ya kike? | Lafiya / Lafiya lau |
| Close | Madallah | Madallah |

The final acknowledgement is followed by a completion button. Morning, afternoon, and evening alternatives are taught on vocabulary cards. This exercise practises initiating the greeting; it does not claim the learner demonstrated the younger person's responses.

## 2. Introductions

The tutor starts with `Ya sunanka?`. The sample tutor name is Musa. The masculine question is a practice role, not a gender inference about the learner.

| Step | Learner | Tutor may reply |
| --- | --- | --- |
| Give a name | Suna na [name] / Sunana [name] | Sannu |
| Ask in return | Kai fa? / Ke fa? / Ya sunanka? | Suna na Musa / Sunana Musa |
| Acknowledge | Sannu | Yauwa |
| Thank | Na gode / Nagode | Na gode |

Both reciprocal forms are accepted; cards explain the male/female addressee distinction. The shared response `Yauwa` comes from the greetings lesson.

## 3. Buying things

The learner is the buyer; the tutor is the seller. The learner points to an item, so no additional item vocabulary is required. Example prices on the cards are ₦100, ₦200, and ₦500; this exercise fixes the price at ₦200.

| Step | Learner | Tutor may reply |
| --- | --- | --- |
| Greet | Sannu | Yauwa |
| Ask price | Nawa ne wannan? / Nawane wannan? | ₦200 |
| Request item | A ba ni / A bani | Na gode |
| Thank seller | Na gode / Nagode | Na gode |

Either party may say thanks: the seller for the purchase, and the buyer for the item. Spoken Hausa number instruction is outside this first exercise.

## 4. Put it all together

`general-practice` combines the three beginner lessons in a shop conversation. The learner is the elder and the tutor is a younger shopkeeper. Recommended after the guided lessons, with no mandatory unlock. The price remains ₦200.

Eight skills can be demonstrated in any order: greeting, time-of-day greeting, asking about wellbeing, giving a name, asking in return, asking the price, requesting the item, and thanking the seller. Repeated phrases receive a reply but count only once. Responses such as `Yauwa`, `Lafiya lau`, `Madallah`, and a ₦200 price check are also accepted without being required for completion. The hint suggests an unpractised skill; it is not a required next step. The learner can finish early for a partial recap.

## Forgiving transcript recognition

The editable `recognition` section of `app/lesson_plans.json` includes explicit examples:

| Recognized input | Lesson phrase |
| --- | --- |
| saanu / sanu | Sannu |
| madala / madalla / madalah | Madallah |
| lafiya law | Lafiya lau |
| toh madallah | Madallah |
| toh bani / toh a bani | A ba ni |

Standalone `toh` / `to` may occur at either edge of a phrase. Case, punctuation, spaces, and written accents are ignored for matching. Longer phrases allow a small edit distance (one edit from six characters, two from twelve); short words and numeric prices require exact text or explicit aliases. Matching covers the entire utterance, so additional unrelated sentences and negations do not pass simply because they contain a taught phrase. Names are handled separately and preserved.

The ASR transcript and learner text remain unchanged in logs. Accepted variants are excluded from spelling corrections in feedback. This is tolerant text recognition, not an acoustic pronunciation or tone assessment. Unrecognized wording gets a hint; it is not labelled a pronunciation mistake. Add more observed variants to the content file as real testers provide examples.

## How replies stay in scope

- The backend owns guided steps and mixed-practice skill tracking, derived from successfully stored turns.
- Learner matching uses the transcript tolerance described above. Unsupported utterances receive a relevant lesson hint and do not advance or count as successful model interactions. The combined mode accepts phrases from all three lessons without requiring a fixed sequence; it is not a general fluency assessment.
- Every successful practice reply is generated by the configured model. Its prompt includes the roles and task, and a JSON schema limits `reply` to that step's permitted responses.
- The backend independently validates the result, retries invalid output once, then reports failure. It never substitutes a canned response and records it as model success.
- Repeated turn IDs return the saved reply and original step state. A completed exercise accepts no further turns; finish or start again.
- Completed tasks in feedback come from demonstrated steps. No pronunciation score is generated.

These controls work with local Ollama. A future Space endpoint must accept the messages and JSON schema, or at least produce the same JSON response for backend validation. It must preserve the backend's lesson instructions.
