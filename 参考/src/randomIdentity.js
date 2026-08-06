const { randomInt } = require('node:crypto');

const firstNames = [
    'Ingrid', 'Leontuzzo', 'Sona', 'Jane', 'Fiona', 'Alexandrina', 'Vina', 'Toru', 'Tylla', 'Chilchuck',
    'Powl', 'Hesheng', 'Anmail', 'Fischer', 'Iwona', 'Loughshinny', 'Cellinia', 'Sonya', 'Ksenia', 'Harmolin',
    'Weiss', 'Rhea', 'Sakiko', 'Pepe', 'Viviana', 'Lessing', 'Shuo', 'Mlynar', 'Anthony', 'Isidore',
    'Zhuhuang', 'Huijie', 'Enciodes', 'Xanthos', 'Nyamu', 'Nuada', 'Laios', 'Gustave', 'Shuhrat', 'Rosalind',
    'Anis', 'Kate', 'Isabelle', 'Ernesto', 'Rafaela', 'Alexsandr', 'Zofia', 'Kemar', 'Ayers', 'Astesia',
    'Beatrix', 'Charlotte', 'Laurentina', 'Lappland', 'Hannah', 'Cheng', 'Xiaohei', 'Randall', 'Shura', 'Patrician',
    'Yu', 'Shu', 'Lavinia', 'Rita', 'Maria', 'Zumama', 'Nian', 'Hoshiguma', 'Fernand', 'Byok',
    'Senshi', 'Secunda', 'Michael', 'Shana', 'Agni', 'William', 'Lola', 'Greynuty', 'Elias', 'Xisheng',
    'Margaret', 'Makayla', 'Rada', 'Matterhorn', 'Bokai', 'Melie', 'Trevor', 'Narantuya', 'Wisadel', 'Rayella',
    'Avdotya', 'Fiammetta', 'Justina', 'Eliza', 'Hildegard', 'Rosmontis', 'Natalya', 'Lemuen', 'Gordon', 'Juana',
    'Bridgit', 'Anna', 'Helena', 'Madeleine', 'Richele', 'Arianrhod', 'Airy', 'Federico', 'Hinterlea', 'Kali',
    'Totter', 'Mina', 'Jessica', 'Aletta', 'Eblana', 'Marcille', 'Aefanyl', 'Yuxia', 'Franz', 'Susie',
    'Elliot', 'Dusk', 'Ceobe', 'Adele', 'Techno', 'Aroma', 'Heinz', 'Delphine', 'Simone', 'Lochsley',
    'Harmony', 'Stitch', 'Astgenne', 'Elena', 'Rochelle', 'Kjeragandr', 'Yar', 'Eleanor', 'Tomimi', 'Ankhana',
    'Leonhardt', 'Zoya', 'Qingyan', 'Rebel', 'Aethelfled', 'Tonia', 'Ragna', 'Aria', 'Mejytikty', 'Jody',
    'Kaltsit', 'Liz', 'Quisartsader', 'Qingping', 'Paskala', 'Anat', 'Harold', 'Magdal', 'Zoe', 'Ningning',
    'Louisa', 'Grace', 'Ceylon', 'Olivia', 'Joyce', 'Lena', 'Gavial', 'Adelle', 'Nasti', 'Haruka',
    'Momoka', 'Serafina', 'Arturia', 'Feist', 'Ling', 'Gnosis', 'Lisa', 'Valenta', 'Angelina', 'Uika',
    'Ningyin', 'Elisio', 'Catherine', 'Lashur', 'Lucilla', 'Elki', 'Deste', 'Gant', 'Heidi', 'Enya',
    'Mayer', 'Roberta', 'Glaciel', 'Eureka', 'Lyudmila', 'Elzbieta', 'Dorothy', 'Weedy', 'Lucian', 'Umiri',
    'Mutsumi', 'Tibi', 'Muriel', 'Luchino', 'Nienke', 'Spuria', 'Ezel', 'Kirara', 'Tina', 'Waaifu',
    'Shensheng', 'Ensia', 'Claudia', 'Verdant', 'Senomy',
    'Alex', 'Misha', 'Talulah', 'Yelena', 'Eno', 'Sasha', 'Buldrokkastee', 'Gray', 'Kristen', 'Rupert',
    'Otto', 'Andoain', 'Clement', 'Kohei', 'Kinbei', 'Amiya', 'Theresa'
];

const lastNames = [
    'Venezia', 'Bellone', 'Willow', 'Young', 'Victoria', 'Moriuchi', 'Timms', 'Andirose', 'Fischer',
    'Krukovska', 'Dublinn', 'Texas', 'Markovna', 'Neryudova', 'Harmolin', 'Togawa', 'Sakhet', 'Hatshepsut', 'Hochberg',
    'Droste', 'Meyer', 'Nearl', 'Simon', 'SilverAsh', 'Gu', 'Chen', 'Yutenji', 'Kateb', 'Kessikbayev',
    'Larina', 'Visser', 'Morrigan', 'Montague', 'Salas', 'Silva', 'Senaviev', 'Ubica', 'Swire', 'Saluzzo',
    'Jackson', 'Hofstadter', 'Orlov', 'Pozzo', 'Falcone', 'Skamandros', 'Byrne', 'Wolfgang', 'Muyman', 'Czerny',
    'Kotz', 'Chunlei', 'Yek', 'Bornu', 'Friston', 'Kapdan', 'Razorpen', 'Ivanova', 'Valentine', 'Cohen',
    'Rostova', 'Tannon', 'Mitterand', 'Columbo', 'Broadweid', 'Giallo', 'Land', 'Brinley', 'Grit', 'Grove',
    'Naumann', 'Rinaldi', 'Windermere', 'Canvas', 'Rockwell', 'Pasbeletti', 'Gloria', 'Montblanc', 'Cranne', 'Fontanarossa',
    'ElAlDin', 'Craigavon', 'Shaw', 'Burris', 'Lin', 'Arizona', 'Doykos', 'Silence', 'Moore',
    'Asupuoro', 'Lunorey', 'Murasaki', 'Hanyu', 'Petrova', 'Edelweiss', 'Magellan', 'Ajimu', 'Misumi',
    'Fletcher', 'Thomson', 'Morozova', 'Stony', 'Baker', 'Wegner', 'Ilyinichna', 'Bosak', 'Franks', 'Pena',
    'Yahata', 'Wakaba', 'Booker', 'DeMontano', 'Meijer', 'Arias', 'Pastore', 'Tsang', 'Wan', 'Artorius',
    'Wright', 'Dietmar', 'Utica', 'Agathanjiross', 'Dubois', 'Mifune', 'Saharada'
];

const passwordCharset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$';

function pickRandom(list) {
    return list[randomInt(list.length)];
}

function generateRandomName() {
    return `${pickRandom(firstNames)} ${pickRandom(lastNames)}`;
}

function generateRandomPassword(length = 16) {
    let password = '';

    for (let index = 0; index < length; index += 1) {
        password += passwordCharset[randomInt(passwordCharset.length)];
    }

    return `${password}A1!`;
}

module.exports = {
    generateRandomName,
    generateRandomPassword,
};
