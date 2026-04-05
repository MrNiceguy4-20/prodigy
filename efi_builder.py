# Updated efi_builder.py

import network_utils
import logger
import input_validator

# Retry logic for failed downloads
RETRY_COUNT = 3

def download_with_retry(url):
    for attempt in range(RETRY_COUNT):
        try:
            response = network_utils.download(url)
            return response
        except Exception as e:
            logger.log(f"Download failed: {str(e)}. Attempt {attempt + 1}/{RETRY_COUNT}")
            if attempt == RETRY_COUNT - 1:
                raise

# Fallback sources for missing kexts
FALLBACK_SOURCES = [
    'https://fallback_source_1.com',
    'https://fallback_source_2.com',
]

def get_kext(kext_name):
    try:
        # Attempt to get the kext from primary source
        return download_with_retry(f'https://primary_source.com/{kext_name}')
    except Exception:
        logger.log(f"Primary source failed for {kext_name}, trying fallback sources...")
        for source in FALLBACK_SOURCES:
            try:
                return download_with_retry(f'{source}/{kext_name}')
            except Exception:
                continue
        logger.log(f"All sources failed for {kext_name}")
        raise

# Better error handling for missing tools
def check_tools(tools):
    for tool in tools:
        if not input_validator.validate_tool(tool):
            logger.log(f"Tool missing: {tool}")
            raise RuntimeError(f"Missing tool: {tool}")
