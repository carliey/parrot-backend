# Beginner Hausa lesson plans

Version: `practice-4`. Vocabulary, English glosses, and cultural guidance follow the project owner's notes of 11 October 2026. They remain marked as draft content awaiting language review. No new pronunciation guides have been invented.

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

Eight skills can be demonstrated in any order: greeting, time-of-day greeting, asking about wellbeing, giving a name, asking in return, asking the price, requesting the item, and thanking the seller. Repeated phrases receive a reply but count only once. Responses such as `Yauwa`, `Lafiya lau`, `Madallah`, and a ₦200 price check are also accepted without being required for completion. The hint suggests an unpractised skill; it is not a required next step. The learner can finish early for a partial recap, or continue chatting after covering all eight skills. Completing the checklist does not end general practice.

## Forgiving transcript recognition in guided lessons

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

## Conversational general practice

General practice sends every nonempty utterance to N-ATLaS with recent conversation history. Exact phrase recognition no longer gates the conversation. The model interprets meaning, combined phrases, paraphrases, fillers, and minor ASR errors. `Kai fa?` / `Ke fa?` is interpreted in context rather than always treated as a name question.

The model returns `{reply, status, skills}`. Status is `understood`, `unclear`, or `off_topic`. Replies for understood turns are generated freely within the beginner lesson instructions: at most 20 words, two short sentences, one question, and at most two unfamiliar words. The backend checks those limits, familiar vocabulary (including learner names), numeric prices, and the elder role. This is a vocabulary/shape guard plus model instructions, not a proof that every reply is linguistically correct or relevant. Hausa speaker review remains necessary.

Unclear and off-topic turns use short English support messages selected by the model through their status. They receive no skill credit. These are conversation repair turns, not transcription errors or pronunciation judgements. If generation fails or returns invalid output twice, the request still fails honestly; no successful model reply is invented.

Skills are independent of reply selection. A model skill claim must contain an exact excerpt from the latest learner text and an allowed skill ID. Fabricated evidence and claims contradicting recognisable phrases are discarded. Familiar whole phrases also retain deterministic recognition; context-dependent `Kai fa?` / `Ke fa?` requires model assessment. More than one skill can count in a turn, each skill counts only once, and replies need not teach the next missing skill. Semantic skill attribution is provisional model feedback, not a verified fluency assessment.

The additive `turn_assessments` SQLite table stores status and evidence alongside each successful general-practice turn. They are returned by local consenting-session exports and reused for progress, finish feedback, and idempotent retries. Original learner and ASR text remain unchanged. Existing database rows are preserved.

## How guided replies stay in scope

- The backend owns guided steps and general-practice skill tracking, derived from successfully stored turns and their assessments.
- Learner matching uses the transcript tolerance described above. Unsupported utterances receive a relevant lesson hint and do not advance or count as successful model interactions.
- Every successful guided practice reply is generated by the configured model. Its prompt includes the roles and task, and a JSON schema limits `reply` to that step's permitted responses.
- The backend independently validates the result, retries invalid output once, then reports failure. It never substitutes a canned response and records it as model success.
- Repeated turn IDs return the saved reply and original step state. A completed guided exercise accepts no further turns; finish or start again. General practice continues until the learner chooses Finish.
- Completed tasks in feedback come from demonstrated steps. No pronunciation score is generated.

These controls work with local Ollama. A future Space endpoint must accept the messages and JSON schema, or at least produce the same JSON response for backend validation. It must preserve the backend's lesson instructions. Guided generation uses `{reply}`; general practice uses `{reply, status, skills}` with evidence, and finish uses the feedback schema. Pass the supplied schema through without hardcoding a reply-only format. The current Ollama context budget is 4096 tokens to fit the conversation instructions, history and structured output.
