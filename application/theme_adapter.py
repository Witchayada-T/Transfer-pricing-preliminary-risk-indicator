"""Generate Streamlit's theme from the single maintained JSON token source."""
from pathlib import Path
import json

def generate(base=None):
    base=Path(base or Path(__file__).parent);tokens=json.loads((base/'theme.json').read_text())
    text='[theme]\nbase = "light"\n'+''.join(key+' = '+json.dumps(tokens[source])+'\n' for key,source in [('primaryColor','primary'),('backgroundColor','background'),('secondaryBackgroundColor','surface'),('textColor','text'),('font','font')])
    text+='\n[browser]\ngatherUsageStats = false\n\n[client]\ntoolbarMode = "minimal"\n'
    target=base/'.streamlit/config.toml';target.parent.mkdir(exist_ok=True);target.write_text(text)
    return text

if __name__=='__main__':generate()
