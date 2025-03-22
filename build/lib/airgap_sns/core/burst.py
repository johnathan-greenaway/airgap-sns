import re, logging
from typing import Optional, Dict
from pydantic import BaseModel, ValidationError

BURST_PATTERN = re.compile(r"!!BURST\(((?:[^;=]+=[^;]*;?)*)\)!!")
ESCAPE_SEQ = re.compile(r"\\(.)")

class BurstParams(BaseModel):
    dest: Optional[str] = None
    wc: Optional[str] = None
    encrypt: bool = False
    webhook: Optional[str] = None
    pwd: Optional[str] = None
    audio: Optional[str] = None

def unescape_param(value: str) -> str:
    return ESCAPE_SEQ.sub(r"\1", value)

def parse_burst(text: str) -> Optional[Dict]:
    try:
        m = BURST_PATTERN.search(text)
        if not m:
            return None
            
        params_str = unescape_param(m.group(1))
        params = {}
        for pair in params_str.split(';'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[key.strip()] = value.strip()
                
        burst_params = BurstParams(**params)
        return burst_params.dict(exclude_unset=True)
        
    except (ValidationError, ValueError) as e:
        logging.error(f"Invalid burst parameters: {str(e)}")
        return None
