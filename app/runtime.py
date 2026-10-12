import os


def validate_runtime():
    """The deployment image cannot select a local inference provider."""
    if os.getenv('PARROT_REMOTE_ONLY', '0') == '1':
        if (os.getenv('PARROT_PROVIDER', 'hf_space') != 'hf_space'
                or os.getenv('PARROT_ASR_PROVIDER', 'hf_space') != 'hf_space'):
            raise RuntimeError('Remote-only deployment requires hf_space for generation and ASR')
