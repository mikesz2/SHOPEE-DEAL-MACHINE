CATEGORY_QUERY_MATRIX = {
    'eletronicos': [
        'fone','headset','smartwatch','caixa de som','carregador','power bank','projetor','tablet','celular',
        'fone bluetooth','fone sem fio','smartwatch digital','caixa de som bluetooth','carregador rapido',
        'power bank portatil','projetor portatil','tablet barato','celular promocao','fone promocao','smartwatch promocao'
    ],
    'casa': [
        'organizador','luminaria','lampada','tapete','cortina','almofada','lençol','toalha','decoracao','varal','cabide',
        'organizador multiuso','organizador cozinha','luminaria led','tapete grande','cortina blackout','jogo de lençol',
        'toalha kit','almofada decorativa','decoracao casa','organizador promocao','achadinhos casa'
    ],
    'cozinha': [
        'air fryer','fritadeira','panela','panela eletrica','pote','organizador cozinha','liquidificador','cafeteira',
        'forma','escorredor','garrafa','copo termico','utensilios','moedor','processador',
        'air fryer promocao','air fryer 4 litros','air fryer 5 litros','panela antiaderente','panela eletrica promocao',
        'pote hermetico kit','organizador cozinha promocao','cafeteira promocao','kit utensilios cozinha','achadinhos cozinha'
    ],
    'beleza': [
        'secador','chapinha','escova','maquiagem','skin care','creme','perfume','modelador','depilador','unhas',
        'secador profissional','chapinha promocao','escova secadora','kit maquiagem','kit skincare','perfume promocao',
        'modelador cabelo','depilador eletrico','produtos unhas','achadinhos beleza'
    ],
    'gamer': [
        'mouse gamer','teclado mecanico','headset gamer','controle','mousepad','suporte monitor','cadeira gamer','microfone gamer','webcam',
        'mouse gamer sem fio','teclado mecanico rgb','headset wireless','controle pc','mousepad grande','cadeira gamer promocao',
        'microfone usb','webcam full hd','achadinhos gamer'
    ],
    'celular': [
        'smartphone','celular','capinha','pelicula','carregador','cabo usb','power bank','suporte celular','fone bluetooth',
        'carregador turbo','carregador 20w','carregador 65w','cabo usb c','capinha anti impacto','pelicula 3d',
        'suporte celular carro','power bank promocao','kit celular','achadinhos celular'
    ],
    'ferramentas': [
        'parafusadeira','furadeira','jogo de ferramentas','chave','alicate','serra','broca','compressor','multimetro','caixa ferramentas',
        'parafusadeira sem fio','furadeira 20v','kit ferramentas','jogo de chaves','alicate profissional','serra eletrica',
        'jogo de brocas','compressor portatil','achadinhos ferramentas'
    ],
    'moda': [
        'camiseta','camisa','calca','bermuda','vestido','tenis','sandalia','bolsa','mochila','conjunto',
        'camiseta promocao','vestido promocao','tenis promocao','bolsa feminina','mochila promocao','conjunto feminino',
        'moda masculina','moda feminina','achadinhos moda'
    ]
}

def expand_category(seed):
    return list(dict.fromkeys(CATEGORY_QUERY_MATRIX.get(seed.strip().lower(), [seed.strip()])))
