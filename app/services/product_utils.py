import re
import unicodedata

CATEGORY_RULES = {
    'eletronicos': ['fone','bluetooth','smartwatch','celular','smartphone','tablet','caixa de som','carregador','cabo usb','power bank','projetor','tv','televis'],
    'gamer': ['gamer','gaming','mouse','teclado','headset','controle','joystick','rgb'],
    'casa': ['casa','organizador','tapete','cortina','luminaria','lampada','almofada','lençol','toalha','decoração','decoracao'],
    'cozinha': ['cozinha','air fryer','fritadeira','panela','liquidificador','cafeteira','copo','garrafa','pote','talher','forno'],
    'beleza': ['beleza','maquiagem','perfume','shampoo','secador','chapinha','escova','creme','skin care','skincare'],
    'ferramentas': ['ferramenta','furadeira','parafusadeira','chave','alicate','serra','broca','compressor'],
    'moda': ['camisa','camiseta','calça','calca','bermuda','vestido','tênis','tenis','sandália','sandalia','bolsa','mochila'],
}


def strip_accents(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text or '') if unicodedata.category(c) != 'Mn')


def normalize_name(text: str) -> str:
    text = strip_accents((text or '').lower())
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    tokens = [t for t in text.split() if len(t) > 1]
    return ' '.join(tokens)


def categorize(name: str) -> str:
    n = normalize_name(name)
    for cat, terms in CATEGORY_RULES.items():
        if any(normalize_name(term) in n for term in terms):
            return cat
    return 'outros'


def token_set(name: str) -> set[str]:
    stop = {'de','da','do','das','dos','com','para','por','em','e','a','o','um','uma','kit','novo','nova'}
    return {t for t in normalize_name(name).split() if t not in stop and len(t) > 2}


def name_similarity(a: str, b: str) -> float:
    aa, bb = token_set(a), token_set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def csv_items(value: str) -> list[str]:
    return [normalize_name(x.strip()) for x in (value or '').split(',') if x.strip()]
