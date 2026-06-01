"""ESIGN disclosure SSOT for onboarding packets.

Mirrors the *shape* of ``proposals.service.proposal_esign_disclosure`` (a
versioned module constant + a function returning blank-line-joined
paragraphs) but NOT its text: the proposal disclosure says "the proposal
above", which is wrong for a W-9 / onboarding form. The public packet page
serves this exact text and the ``/complete`` flow persists it per signature
document, so the stored evidence is byte-identical to what the signer saw.

Structure (counsel-aligned): the text is split into a distinct **E-Consent**
section (consent to transact electronically — the affirmative step) and a
separate **signature** section, followed by the **audit trail**, so the fill
flow can present and record consent as its own step BEFORE the signature is
drawn. For an individual signing for personal/household purposes (a
"consumer"), the ESIGN Act §7001(c) consumer disclosures — a hardware/software
requirements statement and the right to a paper copy — are included; they are
omitted for a business signer.

The codebase has no consumer-vs-business signer distinction yet, so
``signer_type`` defaults to ``"consumer"`` (the disclosure-complete, fail-safe
default — show the consumer block when the signer can't be classified).

NOTE (flow, not text): recording consent as its own affirmative step with its
own audit event — distinct from the signature — is a flow concern handled by
the fill page + ``consented_at`` on the e-sign document; this module only
supplies the text those steps present and snapshot.

WORDING pending Lorenzo / counsel sign-off — bump the version string when the
text changes so older evidence stays attributable.
"""

from typing import Literal

ONBOARDING_ESIGN_DISCLOSURE_VERSION = "2026-06-01.onboarding.v2-consumer-econsent-draft"

# Whether the signer is an individual acting for personal/household purposes
# (``"consumer"`` — ESIGN §7001(c) consumer disclosures apply) or signing on
# behalf of a business (``"business"`` — §7001(c) does not apply).
SignerType = Literal["consumer", "business"]


def onboarding_esign_disclosure(
    *, company_name: str, signer_type: SignerType = "consumer"
) -> str:
    """Full ESIGN disclosure for an onboarding document set.

    Paragraphs are separated by blank lines so the frontend can split and
    render them. ``company_name`` resolves from tenant branding (falling back
    to a neutral label) — never the recipient's own company.

    The text keeps **consent to transact electronically** (the affirmative
    step the signer makes before signing) separate from the **signature act**
    itself. ``signer_type`` gates the ESIGN Act §7001(c) CONSUMER disclosures
    (hardware/software requirements + the right to request a paper copy), which
    are required only when an individual signs for personal/household purposes:
    they render for ``"consumer"`` (the default) and are omitted for
    ``"business"``. The codebase has no signer-type field yet, so callers that
    can't classify the signer should leave the default — the consumer
    disclosures are shown (fail-safe).
    """
    paragraphs: list[str] = []

    # --- Consent to transact electronically (affirmed BEFORE signing) ---
    paragraphs.append(
        "ELECTRONIC RECORDS & SIGNATURES — YOUR CONSENT. Before you sign, you "
        "are agreeing to complete and sign these onboarding documents "
        "electronically and to receive the signed copies electronically, "
        "rather than on paper."
    )

    if signer_type == "consumer":
        # ESIGN Act §7001(c) consumer disclosures (individual / personal use).
        paragraphs.append(
            "To access and keep these electronic records you need: a current "
            "web browser, a PDF reader, a valid email account, and the ability "
            "to download and save (or print) electronic documents. If your "
            "system cannot meet these requirements, you may be unable to sign "
            "electronically."
        )
        paragraphs.append(
            "You have the right to receive these documents on paper instead of "
            "electronically. To request a paper copy, or to update the email "
            f"address used for these records, contact {company_name} directly "
            "before you submit."
        )

    # --- Withdrawal of consent (prospective-only — preserved) ---
    paragraphs.append(
        "You may withdraw your consent to do business electronically by "
        f"contacting {company_name} directly before submitting. Withdrawing "
        "consent applies going forward only and does not retroactively "
        "invalidate signatures already captured."
    )

    # --- The signature act (separate from the consent above) ---
    paragraphs.append(
        "YOUR ELECTRONIC SIGNATURE. By drawing and submitting your signature, "
        "you confirm that you have read each document in this onboarding set, "
        "and you agree that this constitutes your legally binding electronic "
        "signature under the US ESIGN Act (15 USC §7001) and applicable state "
        "UETA statutes, with the same legal effect as a handwritten signature."
    )

    # --- Audit trail (unchanged) ---
    paragraphs.append(
        "We record your name, email address, IP address, browser user-agent, "
        "and timestamp at submission. This audit trail is retained alongside "
        "your completed documents for dispute resolution."
    )

    return "\n\n".join(paragraphs)
