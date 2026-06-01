"""Client Onboarding feature (Phases 1-2).

See CLIENT_ONBOARDING_PLAN.md §14. Phase 1 provides the onboarding template
library (model + CRUD), the storage abstraction, and the PDF field stamper.
Phase 2 adds per-recipient *packets* (a token-gated copy of one or more
templates the client fills + e-signs from a public link), the public fill
flow with a bearer session + read-before-sign view ledger, the 3-phase
``/complete`` with per-document atomic lease, and the proxied completion
download. The invite-auto-send trigger (on e-sign) is Phase 3.
"""
