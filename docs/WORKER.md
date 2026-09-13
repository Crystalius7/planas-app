# The paid-tier digest worker: the owner's PC vs a cloud model (2026-09-13)

The free tier never needs a worker: the baseline digest (no AI) and Ollama run on the student's own computer. The
question is only where the PAID tier's model run happens while there are few users. The owner asked for the pros and
cons of using his own PC as that worker "until we get lots of users".

## Owner's PC as the worker (`product/worker/`, pulls encrypted jobs from the API, runs the engine, pushes results)

**Pros**
- Zero model cost if it runs a local model (Ollama, Gemma/Qwen 9B+): the subscription is pure margin at first.
- Nothing new to rent; the PC already runs the personal system's scheduled tasks around the clock.
- Full control and full logs; the same engine the owner already trusts; debugging is on hand.
- Cloud API keys, spending caps and provider terms are not needed until the tier grows.

**Cons**
- **Other students' course material is processed on a private computer.** Legally possible (GDPR allows it with proper
  security; docs/LEGAL.md §1) but it must be disclosed in the privacy policy as a named processing location and it changes
  the "stays on your device" promise into "sent to our processing computer, deleted after the job" for the paid tier.
- **Availability = the PC's uptime.** Asleep, updating, travelling → jobs wait; the app must show "delayed" (it does:
  API jobs answer "processing is delayed while no worker is online"). A student paying before a test expects minutes,
  not "when the PC wakes".
- **Security surface.** A home PC becomes a data processor: full-disk encryption, a dedicated OS user for the worker,
  no other family use, tested backups/deletion, and an incident plan. A compromise would leak many students' material.
- **Quality and speed of a local model.** Lithuanian and other small languages need a 9B+ model; on a CPU that is
  minutes per subject-month and lower quality than a cloud model; a GPU with ~6 GB VRAM is the realistic minimum.
- **Scaling cliff.** One PC serves maybe 20-50 active students; the moment the tier works, the worker has to move anyway,
  so the cloud path must exist from day one (it does: the worker reads the same job queue a server would).
- **Mixing with the owner's own study data.** The worker must run in its own workspace folder and OS user; the personal
  system's secrets and courses are never reachable from it.

## Cloud model API with a spending cap

**Pros:** minutes not hours, nothing on the owner's PC, no processing-location disclosure beyond "our contracted model
provider", scales with users, cost is tiny at 5 € pricing (0.05-0.40 $ per subject-month with a cheap capable model).
**Cons:** needs one API key and a card at the provider (a spend the owner must green-light; a hard monthly cap keeps it
bounded), provider terms must be reviewed for student data (no training on inputs), and the first month runs at a loss
until subscriptions cover it.

## Recommendation

Start the paid tier on a **cloud model with a hard monthly cap** (e.g. 20 €) and keep the **owner's PC as the OFFLINE
fallback worker** for the local Ollama route, not as the primary processor of other students' material. If the owner
prefers his PC as primary anyway: run it under a separate Windows user with BitLocker on, only Ollama (no course text
leaves the machine), the privacy policy names it as a processing location, and the app promises "within 24 h" for paid
digests. Both paths use the same `product/worker/` job loop; only the provider setting differs.
