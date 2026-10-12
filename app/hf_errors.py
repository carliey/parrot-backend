"""Convert Hugging Face ZeroGPU quota errors into safe app messages."""
import re


_ZERO_GPU_QUOTA = re.compile(
    r"exceeded your [^\n]*?ZeroGPU quota\s*\(\s*(\d+(?:\.\d+)?)s requested\s+vs\.\s*(-?\d+(?:\.\d+)?)s left\)\.\s*Try again in\s+([^\n.]+)",
    re.IGNORECASE,
)


class HuggingFaceQuotaError(RuntimeError):
    """A remote ZeroGPU job was refused because the account quota is low."""


def quota_error_message(error: BaseException) -> str | None:
    match = _ZERO_GPU_QUOTA.search(str(error))
    if not match:
        return None
    requested, remaining, retry_in = match.groups()
    return (
        'Hugging Face GPU quota is too low for this request '
        f'({requested} seconds needed; {remaining} seconds remain). '
        f'Try again in {retry_in.strip()}.'
    )
