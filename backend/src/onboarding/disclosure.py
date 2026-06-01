"""ESIGN disclosure SSOT for onboarding packets.

Mirrors the *shape* of ``proposals.service.proposal_esign_disclosure`` (a
versioned module constant + a function returning blank-line-joined
paragraphs) but NOT its text: the proposal disclosure says "the proposal
above", which is wrong for a W-9 / onboarding form. The public packet page
serves this exact text and the ``/complete`` flow persists it per signature
document, so the stored evidence is byte-identical to what the signer saw.

WORDING IS A PLACEHOLDER pending Lorenzo / counsel sign-off — bump the
version string when the text changes so older evidence stays attributable.
"""

ONBOARDING_ESIGN_DISCLOSURE_VERSION = "2026-06-01.onboarding.v1-draft"


def onboarding_esign_disclosure(*, company_name: str) -> str:
    """Full ESIGN disclosure for an onboarding document set.

    Paragraphs are separated by blank lines so the frontend can split and
    render them. ``company_name`` resolves from tenant branding (falling back
    to a neutral label) — never the recipient's own company.
    """
    return "\n\n".join(
        (
            "By drawing and submitting your signature, you confirm that you "
            "have read each document in this onboarding set, and you agree "
            "that this constitutes your legally binding electronic signature "
            "under the US ESIGN Act (15 USC §7001) and applicable state UETA "
            "statutes, with the same legal effect as a handwritten signature.",
            "You consent to complete and sign these documents electronically "
            f"and to receive signed copies electronically. You may withdraw "
            f"consent by contacting {company_name} directly before submitting "
            "— this does not retroactively invalidate signatures already "
            "captured.",
            "We record your name, email address, IP address, browser "
            "user-agent, and timestamp at submission. This audit trail is "
            "retained alongside your completed documents for dispute "
            "resolution.",
        )
    )
