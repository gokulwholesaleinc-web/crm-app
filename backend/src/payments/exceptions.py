"""Domain exceptions for the payments module.

Hosted in their own module so that both `payments.service` and
`payments.webhook_processor` can import them without forming an import
cycle (the two modules already import each other lazily for the
PaymentService↔WebhookProcessor pair).
"""


class NoRecipientEmailError(ValueError):
    """Send was attempted against a payment whose customer has no email.

    Subclass so webhook callers can swallow this case narrowly without
    masking unrelated `ValueError`s from template rendering, decimal
    parsing, or Pydantic validation.
    """
