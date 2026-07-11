"""
Preset ticker universes, organized per-exchange, plus tools for loading a
complete/custom ticker list from a CSV file.

yfinance tickers for non-US exchanges need a suffix, e.g.:
  .L   London Stock Exchange
  .DE  Deutsche Boerse / XETRA (Germany)
  .PA  Euronext Paris
  .AS  Euronext Amsterdam
  .MI  Borsa Italiana (Milan)
  .SW  SIX Swiss Exchange
  .MC  Bolsa de Madrid
  .ST  Nasdaq Stockholm
  .BR  Euronext Brussels
  .OL  Oslo Bors
  .CO  Nasdaq Copenhagen
  .HE  Nasdaq Helsinki
  .LS  Euronext Lisbon
  .VI  Wiener Borse (Vienna)
  .IR  Euronext Dublin

IMPORTANT ON COMPLETENESS: the dicts below are curated lists of well-known,
liquid names per exchange -- they are NOT guaranteed to be the full,
exhaustive list of every company listed on that exchange (small/micro caps
in particular get added, renamed, or delisted often). For a fully complete
list of a given exchange:
  1. Download the constituent list from the exchange itself (e.g. Nasdaq
     Nordic's own instrument list at https://www.nasdaqomxnordic.com, or
     your broker's export), as a CSV with at least a 'symbol' column.
  2. Use `load_tickers_from_csv(...)` below to import it.
This keeps ticker accuracy the responsibility of an authoritative source
rather than a hardcoded guess that can go stale.
"""
import csv
import requests

# ---------------------------------------------------------------------------
# Per-exchange curated ticker dicts: {symbol: (name, exchange_label, currency, sector)}
# ---------------------------------------------------------------------------

XETRA = {  # Germany
    "SAP.DE": ("SAP SE", "XETRA", "EUR", "Technology"),
    "SIE.DE": ("Siemens AG", "XETRA", "EUR", "Industrials"),
    "ALV.DE": ("Allianz SE", "XETRA", "EUR", "Financials"),
    "DTE.DE": ("Deutsche Telekom AG", "XETRA", "EUR", "Communication"),
    "BAS.DE": ("BASF SE", "XETRA", "EUR", "Materials"),
    "BMW.DE": ("BMW AG", "XETRA", "EUR", "Consumer Discretionary"),
    "VOW3.DE": ("Volkswagen AG", "XETRA", "EUR", "Consumer Discretionary"),
    "MBG.DE": ("Mercedes-Benz Group", "XETRA", "EUR", "Consumer Discretionary"),
    "MUV2.DE": ("Munich Re", "XETRA", "EUR", "Financials"),
    "ADS.DE": ("Adidas AG", "XETRA", "EUR", "Consumer Discretionary"),
    "DHL.DE": ("DHL Group", "XETRA", "EUR", "Industrials"),
    "IFX.DE": ("Infineon Technologies", "XETRA", "EUR", "Technology"),
    "BAYN.DE": ("Bayer AG", "XETRA", "EUR", "Healthcare"),
    "RWE.DE": ("RWE AG", "XETRA", "EUR", "Utilities"),
}

EURONEXT_PARIS = {  # France
    "MC.PA": ("LVMH", "EURONEXT PARIS", "EUR", "Consumer Discretionary"),
    "OR.PA": ("L'Oreal", "EURONEXT PARIS", "EUR", "Consumer Staples"),
    "SAN.PA": ("Sanofi", "EURONEXT PARIS", "EUR", "Healthcare"),
    "AI.PA": ("Air Liquide", "EURONEXT PARIS", "EUR", "Materials"),
    "TTE.PA": ("TotalEnergies", "EURONEXT PARIS", "EUR", "Energy"),
    "BNP.PA": ("BNP Paribas", "EURONEXT PARIS", "EUR", "Financials"),
    "AIR.PA": ("Airbus SE", "EURONEXT PARIS", "EUR", "Industrials"),
    "DG.PA": ("Vinci SA", "EURONEXT PARIS", "EUR", "Industrials"),
    "SU.PA": ("Schneider Electric", "EURONEXT PARIS", "EUR", "Industrials"),
    "CS.PA": ("AXA SA", "EURONEXT PARIS", "EUR", "Financials"),
    "KER.PA": ("Kering SA", "EURONEXT PARIS", "EUR", "Consumer Discretionary"),
}

EURONEXT_AMSTERDAM = {  # Netherlands
    "ASML.AS": ("ASML Holding", "EURONEXT AMSTERDAM", "EUR", "Technology"),
    "AD.AS": ("Ahold Delhaize", "EURONEXT AMSTERDAM", "EUR", "Consumer Staples"),
    "INGA.AS": ("ING Groep", "EURONEXT AMSTERDAM", "EUR", "Financials"),
    "PHIA.AS": ("Philips", "EURONEXT AMSTERDAM", "EUR", "Healthcare"),
    "HEIA.AS": ("Heineken", "EURONEXT AMSTERDAM", "EUR", "Consumer Staples"),
}

BORSA_ITALIANA = {  # Italy
    "ENI.MI": ("Eni SpA", "BORSA ITALIANA", "EUR", "Energy"),
    "ISP.MI": ("Intesa Sanpaolo", "BORSA ITALIANA", "EUR", "Financials"),
    "ENEL.MI": ("Enel SpA", "BORSA ITALIANA", "EUR", "Utilities"),
    "RACE.MI": ("Ferrari NV", "BORSA ITALIANA", "EUR", "Consumer Discretionary"),
    "UCG.MI": ("UniCredit", "BORSA ITALIANA", "EUR", "Financials"),
}

BOLSA_MADRID = {  # Spain
    "ITX.MC": ("Inditex", "BOLSA DE MADRID", "EUR", "Consumer Discretionary"),
    "SAN.MC": ("Banco Santander", "BOLSA DE MADRID", "EUR", "Financials"),
    "IBE.MC": ("Iberdrola", "BOLSA DE MADRID", "EUR", "Utilities"),
    "BBVA.MC": ("BBVA", "BOLSA DE MADRID", "EUR", "Financials"),
}

SIX_SWISS = {  # Switzerland
    "NESN.SW": ("Nestle SA", "SIX", "CHF", "Consumer Staples"),
    "ROG.SW": ("Roche Holding", "SIX", "CHF", "Healthcare"),
    "NOVN.SW": ("Novartis AG", "SIX", "CHF", "Healthcare"),
    "UBSG.SW": ("UBS Group", "SIX", "CHF", "Financials"),
    "ZURN.SW": ("Zurich Insurance", "SIX", "CHF", "Financials"),
}

LSE = {  # United Kingdom
    "SHEL.L": ("Shell plc", "LSE", "GBP", "Energy"),
    "AZN.L": ("AstraZeneca", "LSE", "GBP", "Healthcare"),
    "HSBA.L": ("HSBC Holdings", "LSE", "GBP", "Financials"),
    "ULVR.L": ("Unilever", "LSE", "GBP", "Consumer Staples"),
    "BP.L": ("BP plc", "LSE", "GBP", "Energy"),
    "GSK.L": ("GSK plc", "LSE", "GBP", "Healthcare"),
    "DGE.L": ("Diageo", "LSE", "GBP", "Consumer Staples"),
    "RIO.L": ("Rio Tinto", "LSE", "GBP", "Materials"),
    "BATS.L": ("British American Tobacco", "LSE", "GBP", "Consumer Staples"),
    "VOD.L": ("Vodafone Group", "LSE", "GBP", "Communication"),
}

NASDAQ_STOCKHOLM = {  # Sweden
    "ERIC-B.ST": ("Ericsson", "NASDAQ STOCKHOLM", "SEK", "Technology"),
    "VOLV-B.ST": ("Volvo AB", "NASDAQ STOCKHOLM", "SEK", "Industrials"),
    "ATCO-A.ST": ("Atlas Copco A", "NASDAQ STOCKHOLM", "SEK", "Industrials"),
    "INVE-B.ST": ("Investor AB B", "NASDAQ STOCKHOLM", "SEK", "Financials"),
    "SEB-A.ST": ("SEB A", "NASDAQ STOCKHOLM", "SEK", "Financials"),
    "SWED-A.ST": ("Swedbank A", "NASDAQ STOCKHOLM", "SEK", "Financials"),
    "HM-B.ST": ("H&M B", "NASDAQ STOCKHOLM", "SEK", "Consumer Discretionary"),
    "SAND.ST": ("Sandvik AB", "NASDAQ STOCKHOLM", "SEK", "Industrials"),
    "TELIA.ST": ("Telia Company", "NASDAQ STOCKHOLM", "SEK", "Communication"),
    "SHB-A.ST": ("Svenska Handelsbanken A", "NASDAQ STOCKHOLM", "SEK", "Financials"),
}

NASDAQ_COPENHAGEN = {  # Denmark
    "NOVO-B.CO": ("Novo Nordisk", "NASDAQ COPENHAGEN", "DKK", "Healthcare"),
    "MAERSK-B.CO": ("A.P. Moller-Maersk B", "NASDAQ COPENHAGEN", "DKK", "Industrials"),
    "DSV.CO": ("DSV A/S", "NASDAQ COPENHAGEN", "DKK", "Industrials"),
    "ORSTED.CO": ("Orsted A/S", "NASDAQ COPENHAGEN", "DKK", "Utilities"),
    "CARL-B.CO": ("Carlsberg B", "NASDAQ COPENHAGEN", "DKK", "Consumer Staples"),
    "GN.CO": ("GN Store Nord", "NASDAQ COPENHAGEN", "DKK", "Healthcare"),
    "COLO-B.CO": ("Coloplast B", "NASDAQ COPENHAGEN", "DKK", "Healthcare"),
}

OSLO_BORS = {  # Norway
    "EQNR.OL": ("Equinor ASA", "OSLO BORS", "NOK", "Energy"),
    "DNB.OL": ("DNB Bank ASA", "OSLO BORS", "NOK", "Financials"),
    "TEL.OL": ("Telenor ASA", "OSLO BORS", "NOK", "Communication"),
    "MOWI.OL": ("Mowi ASA", "OSLO BORS", "NOK", "Consumer Staples"),
    "NHY.OL": ("Norsk Hydro ASA", "OSLO BORS", "NOK", "Materials"),
    "ORK.OL": ("Orkla ASA", "OSLO BORS", "NOK", "Consumer Staples"),
    "YAR.OL": ("Yara International", "OSLO BORS", "NOK", "Materials"),
}

NASDAQ_HELSINKI = {
    # Snapshot of all ~192 tickers listed on Nasdaq Helsinki, sourced from
    # stockanalysis.com/list/nasdaq-helsinki (July 2026). This is a full
    # exchange listing at time of writing, not just blue chips -- but it
    # WILL drift out of date (delistings, renames, new listings). A few of
    # these are dual-listed Nordic companies (e.g. Ericsson, Nordea, SSAB,
    # Telia) whose primary Yahoo Finance listing may be on another exchange
    # (e.g. Stockholm) -- their ".HE" ticker may return no data even though
    # the company itself is real and tradeable. fetch_and_store() reports
    # per-symbol errors without failing the whole batch, so this is safe to
    # fetch as-is; just expect a handful of no-data errors in the summary.
    # For a guaranteed-current list, re-export from Nasdaq Nordic yourself
    # and use `python cli.py fetch --csv your_list.csv`.
    'NOKIA.HE': ('Nokia Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'NDA-FI.HE': ('Nordea Bank Abp', 'NASDAQ HELSINKI', 'EUR', ''),
    'ERIBR.HE': ('Telefonaktiebolaget LM Ericsson (publ)', 'NASDAQ HELSINKI', 'EUR', ''),
    'KNEBV.HE': ('KONE Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SAMPO.HE': ('Sampo Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'NESTE.HE': ('Neste Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'WRT1V.HE': ('Wärtsilä Oyj Abp', 'NASDAQ HELSINKI', 'EUR', ''),
    'FORTUM.HE': ('Fortum Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TELIA1.HE': ('Telia Company AB (publ)', 'NASDAQ HELSINKI', 'EUR', ''),
    'UPM.HE': ('UPM-Kymmene Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'METSO.HE': ('Metso Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ORNBV.HE': ('Orion Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ORNAV.HE': ('Orion Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SSABAH.HE': ('SSAB AB (publ)', 'NASDAQ HELSINKI', 'EUR', ''),
    'SSABBH.HE': ('SSAB AB (publ)', 'NASDAQ HELSINKI', 'EUR', ''),
    'KESKOA.HE': ('Kesko Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KESKOB.HE': ('Kesko Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'STEAV.HE': ('Stora Enso Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'STERV.HE': ('Stora Enso Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KCR.HE': ('Konecranes Plc', 'NASDAQ HELSINKI', 'EUR', ''),
    'ELISA.HE': ('Elisa Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'VALMT.HE': ('Valmet Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'HIAB.HE': ('Hiab Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'OUT1V.HE': ('Outokumpu Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'HUH1V.HE': ('Huhtamäki Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KALMAR.HE': ('Kalmar Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'MANTA.HE': ('Mandatum Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KEMIRA.HE': ('Kemira Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TIETO.HE': ('Tieto Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'VAIAS.HE': ('Vaisala Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'LUMO.HE': ('Lumo Kodit Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TYRES.HE': ('Nokian Renkaat Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SANOMA.HE': ('Sanoma Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'BITTI.HE': ('Bittium Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'PUUILO.HE': ('Puuilo Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ALMA.HE': ('Alma Media Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'FSKRS.HE': ('Fiskars Oyj Abp', 'NASDAQ HELSINKI', 'EUR', ''),
    'METSA.HE': ('Metsä Board Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'METSB.HE': ('Metsä Board Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TTALO.HE': ('Terveystalo Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'AKTIA.HE': ('Aktia Pankki Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SCANFL.HE': ('Scanfil Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'FIA1S.HE': ('Finnair Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'HARVIA.HE': ('Harvia Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KEMPOWR.HE': ('Kempower Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'QTCOM.HE': ('Qt Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'GRK.HE': ('GRK Infra Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ALBBV.HE': ('Ålandsbanken Abp', 'NASDAQ HELSINKI', 'EUR', ''),
    'ALBAV.HE': ('Ålandsbanken Abp', 'NASDAQ HELSINKI', 'EUR', ''),
    'OLVAS.HE': ('Olvi Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'PON1V.HE': ('Ponsse Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'EVLI.HE': ('Evli Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'YIT.HE': ('YIT Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'FRAMERY.HE': ('Framery Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'MUSTI.HE': ('Musti Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'CTY1S.HE': ('Citycon Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TALLINK.HE': ('AS Tallink Grupp', 'NASDAQ HELSINKI', 'EUR', ''),
    'MEKKO.HE': ('Marimekko Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ATRAV.HE': ('Atria Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TOKMAN.HE': ('Tokmanni Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'RAIKV.HE': ('Raisio plc', 'NASDAQ HELSINKI', 'EUR', ''),
    'RAIVV.HE': ('Raisio plc', 'NASDAQ HELSINKI', 'EUR', ''),
    'OMASP.HE': ('Oma Säästöpankki Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'EQV1V.HE': ('eQ Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'POSTI.HE': ('Posti Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'FSECURE.HE': ('F-Secure Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'LINDEX.HE': ('Lindex Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ENENTO.HE': ('Enento Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'VIK1V.HE': ('Viking Line Abp', 'NASDAQ HELSINKI', 'EUR', ''),
    'REG1V.HE': ('Revenio Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'PAMPALO.HE': ('Endomines Finland Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'CAPMAN.HE': ('CapMan Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'CANATU.HE': ('Canatu Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'RELAIS.HE': ('Relais Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ICP1V.HE': ('Incap Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'LASTIK.HE': ('Lassila & Tikanoja Plc', 'NASDAQ HELSINKI', 'EUR', ''),
    'PIHLIS.HE': ('Pihlajalinna Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'UNITED.HE': ('United Bankers Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ANORA.HE': ('Anora Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'AUROORA.HE': ('Auroora Yhtiöt Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KOSKI.HE': ('Koskisen Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TAALA.HE': ('Taaleri Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'REMEDY.HE': ('Remedy Entertainment Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ASPO.HE': ('Aspo Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ETTE.HE': ('Etteplan Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KREATE.HE': ('Kreate Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'GOFORE.HE': ('Gofore Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ORIOLA.HE': ('Oriola Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SOSI1.HE': ('Sotkamo Silver AB', 'NASDAQ HELSINKI', 'EUR', ''),
    'DIGIA.HE': ('Digia Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'NOHO.HE': ('NoHo Partners Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ADMCM.HE': ('Admicom Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'HKFOODS.HE': ('HKFoods Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SFOODS.HE': ('Solar Foods Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'DETEC.HE': ('Detection Technology Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TEM1V.HE': ('Tecnotree Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ALEX.HE': ('Alexandria Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'CITYVA.HE': ('Cityvarasto Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'VERK.HE': ('Verkkokauppa.com Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SSH1V.HE': ('SSH Communications Security Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'FARON.HE': ('Faron Pharmaceuticals Oy', 'NASDAQ HELSINKI', 'EUR', ''),
    'KSL.HE': ('Keskisuomalainen Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ILKKA.HE': ('Ilkka Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SITOWS.HE': ('Sitowise Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SRV1V.HE': ('SRV Yhtiöt Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'RAUTE.HE': ('Raute Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'LEMON.HE': ('Lemonsoft Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'CONSTI.HE': ('Consti Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SBI.HE': ('Sunborn International Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'APETIT.HE': ('Apetit Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ORTHEX.HE': ('Orthex Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'EXEL.HE': ('Exel Composites Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'NANOFH.HE': ('Nanoform Finland Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ASUNTO.HE': ('Asuntosalkku Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'NXTMH.HE': ('Nexstim Plc', 'NASDAQ HELSINKI', 'EUR', ''),
    'LUOTEA.HE': ('Luotea Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'LOIHDE.HE': ('Loihde Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'VIAFIN.HE': ('Viafin Service Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'NLG1V.HE': ('Nurminen Logistics Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'AFAGR.HE': ('Afarak Group SE', 'NASDAQ HELSINKI', 'EUR', ''),
    'TITAN.HE': ('Titanium Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ESENSE.HE': ('Enersense International Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KAMUX.HE': ('Kamux Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TLT1V.HE': ('Teleste Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SUY1V.HE': ('Suominen Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ARVOSK.HE': ('Pohjanmaan Arvo Sijoitusosuuskunta', 'NASDAQ HELSINKI', 'EUR', ''),
    'AIFORIA.HE': ('Aiforia Technologies Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'LAPWALL.HE': ('LapWall Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'CTH1V.HE': ('Componenta Corporation', 'NASDAQ HELSINKI', 'EUR', ''),
    'TOIVO.HE': ('Toivo Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TNOM.HE': ('Talenom Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'BOREO.HE': ('Boreo Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TEKOVA.HE': ('Tekova Oy', 'NASDAQ HELSINKI', 'EUR', ''),
    'HEALTH.HE': ('Nightingale Health Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SAGCV.HE': ('Saga Furs Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'MODU.HE': ('Modulight Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'HRTIS.HE': ('Herantis Pharma Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'RAP1V.HE': ('Rapala VMC Corporation', 'NASDAQ HELSINKI', 'EUR', ''),
    'GLA1V.HE': ('Glaston Oyj Abp', 'NASDAQ HELSINKI', 'EUR', ''),
    'SPRING.HE': ('Springvest Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TAMTRON.HE': ('Tamtron Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'BIOBV.HE': ('Biohit Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ACG1V.HE': ('Aspocomp Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ADMIN.HE': ('Administer Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'FODELIA.HE': ('Fodelia Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'MERUS.HE': ('Merus Power Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TULAV.HE': ('Tulikivi Corporation', 'NASDAQ HELSINKI', 'EUR', ''),
    'AALLON.HE': ('Aallon Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KHG.HE': ('KH Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'FOAMIT.HE': ('Foamit Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'OPTOMED.HE': ('Optomed Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SUMMA.HE': ('Summa Defence Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'INDERES.HE': ('Inderes Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ROBIT.HE': ('Robit Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'BRETEC.HE': ('Bioretec Oy', 'NASDAQ HELSINKI', 'EUR', ''),
    'DWF.HE': ('Digital Workforce Services Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'EASOR.HE': ('Easor Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'BETOLAR.HE': ('Betolar Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'WETTERI.HE': ('Wetteri Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'LAMOR.HE': ('Lamor Corporation Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'WITTED.HE': ('Witted Megacorp Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'BEER.HE': ('Nokian Panimo Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'WUF1V.HE': ('Wulff-Yhtiöt Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'REKA.HE': ('Reka Industrial Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'EEZY.HE': ('Eezy Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'OVARO.HE': ('Ovaro Kiinteistösijoitus Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'INVEST.HE': ('Investors House Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SPINN.HE': ('Spinnova Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SOLWERS.HE': ('Solwers Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'EAGLE.HE': ('Eagle Filters Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'SIILI.HE': ('Siili Solutions Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ALISA.HE': ('Alisa Pankki Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'LEADD.HE': ('LeadDesk Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'FONDIA.HE': ('Fondia Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'KELAS.HE': ('Kesla Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'PNA1V.HE': ('Panostaja Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'VINCIT.HE': ('Vincit Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'NETUM.HE': ('Netum Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'NORRH.HE': ('Norrhydro Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'HONBS.HE': ('Honkarakenne Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'REBL.HE': ('Rebl Group Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ECOUP.HE': ('EcoUp Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'QPR1V.HE': ('QPR Software Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'ELEAV.HE': ('Elecster Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'DUELL.HE': ('Duell Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'DOV1V.HE': ('Dovre Group Plc', 'NASDAQ HELSINKI', 'EUR', ''),
    'DIGIGR.HE': ('Digitalist Group Plc', 'NASDAQ HELSINKI', 'EUR', ''),
    'SOLTEQ.HE': ('Solteq Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'TRH1V.HE': ('Trainers\' House Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'PIIPPO.HE': ('Piippo Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'MARAS.HE': ('Martela Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
    'PALLAS.HE': ('Pallas Air Oyj', 'NASDAQ HELSINKI', 'EUR', ''),
}

# Registry of all curated exchange dicts, keyed by a short code you pass to
# `--exchange` on the CLI or `get_exchange_tickers(...)` below.
EXCHANGE_REGISTRY = {
    "XETRA": XETRA,
    "EURONEXT_PARIS": EURONEXT_PARIS,
    "EURONEXT_AMSTERDAM": EURONEXT_AMSTERDAM,
    "BORSA_ITALIANA": BORSA_ITALIANA,
    "BOLSA_MADRID": BOLSA_MADRID,
    "SIX": SIX_SWISS,
    "LSE": LSE,
    "NASDAQ_STOCKHOLM": NASDAQ_STOCKHOLM,
    "NASDAQ_COPENHAGEN": NASDAQ_COPENHAGEN,
    "OSLO_BORS": OSLO_BORS,
    "NASDAQ_HELSINKI": NASDAQ_HELSINKI,
}

# Backwards-compatible combined EU dict (used by get_universe("EU"))
EU_BLUE_CHIPS = {}
for _d in EXCHANGE_REGISTRY.values():
    EU_BLUE_CHIPS.update(_d)

# A reasonably broad set of liquid US large caps as a fallback if the live
# Wikipedia S&P 500 fetch is unavailable.
US_LARGE_CAP_FALLBACK = {
    "AAPL": ("Apple Inc.", "NASDAQ", "USD", "Technology"),
    "MSFT": ("Microsoft Corp.", "NASDAQ", "USD", "Technology"),
    "GOOGL": ("Alphabet Inc.", "NASDAQ", "USD", "Communication"),
    "AMZN": ("Amazon.com Inc.", "NASDAQ", "USD", "Consumer Discretionary"),
    "NVDA": ("NVIDIA Corp.", "NASDAQ", "USD", "Technology"),
    "META": ("Meta Platforms", "NASDAQ", "USD", "Communication"),
    "TSLA": ("Tesla Inc.", "NASDAQ", "USD", "Consumer Discretionary"),
    "BRK-B": ("Berkshire Hathaway", "NYSE", "USD", "Financials"),
    "JPM": ("JPMorgan Chase", "NYSE", "USD", "Financials"),
    "V": ("Visa Inc.", "NYSE", "USD", "Financials"),
    "UNH": ("UnitedHealth Group", "NYSE", "USD", "Healthcare"),
    "XOM": ("Exxon Mobil", "NYSE", "USD", "Energy"),
    "JNJ": ("Johnson & Johnson", "NYSE", "USD", "Healthcare"),
    "PG": ("Procter & Gamble", "NYSE", "USD", "Consumer Staples"),
    "MA": ("Mastercard Inc.", "NYSE", "USD", "Financials"),
    "HD": ("Home Depot", "NYSE", "USD", "Consumer Discretionary"),
    "AVGO": ("Broadcom Inc.", "NASDAQ", "USD", "Technology"),
    "MRK": ("Merck & Co.", "NYSE", "USD", "Healthcare"),
    "PEP": ("PepsiCo Inc.", "NASDAQ", "USD", "Consumer Staples"),
    "COST": ("Costco Wholesale", "NASDAQ", "USD", "Consumer Staples"),
    "ABBV": ("AbbVie Inc.", "NYSE", "USD", "Healthcare"),
    "KO": ("Coca-Cola Co.", "NYSE", "USD", "Consumer Staples"),
    "ADBE": ("Adobe Inc.", "NASDAQ", "USD", "Technology"),
    "WMT": ("Walmart Inc.", "NYSE", "USD", "Consumer Staples"),
    "CRM": ("Salesforce Inc.", "NYSE", "USD", "Technology"),
    "BAC": ("Bank of America", "NYSE", "USD", "Financials"),
    "NFLX": ("Netflix Inc.", "NASDAQ", "USD", "Communication"),
    "AMD": ("Advanced Micro Devices", "NASDAQ", "USD", "Technology"),
    "DIS": ("Walt Disney Co.", "NYSE", "USD", "Communication"),
    "PFE": ("Pfizer Inc.", "NYSE", "USD", "Healthcare"),
    "INTC": ("Intel Corp.", "NASDAQ", "USD", "Technology"),
}


def fetch_sp500_tickers():
    """
    Try to scrape the current S&P 500 constituent list from Wikipedia.
    Falls back to a hardcoded list of large caps if the request fails
    (e.g. no network access).

    Returns a dict {symbol: (name, exchange, currency, sector)}.
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        import pandas as pd
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        tables = pd.read_html(resp.text)
        df = tables[0]
        result = {}
        for _, row in df.iterrows():
            symbol = str(row["Symbol"]).replace(".", "-")  # yfinance uses BRK-B not BRK.B
            name = str(row.get("Security", symbol))
            sector = str(row.get("GICS Sector", ""))
            result[symbol] = (name, "NYSE/NASDAQ", "USD", sector)
        if result:
            return result
    except Exception:
        pass
    return dict(US_LARGE_CAP_FALLBACK)


def fetch_nasdaq_full_tickers(include_etfs: bool = False, include_test_issues: bool = False) -> dict:
    """
    Fetches the COMPLETE, officially published list of every security
    natively listed on the Nasdaq exchange (not just the S&P 500 subset) --
    typically several thousand tickers, including many small/micro caps,
    SPACs, ADRs, warrants, and units.

    Source: Nasdaq's own public Symbol Directory
    (https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt), the
    same reference data feed used by most third-party finance tools. It's
    updated by Nasdaq multiple times per day, so this is fetched live
    rather than hardcoded.

    By default this excludes ETFs and test issues to keep the universe to
    common stocks; pass include_etfs=True to keep ETFs too.

    WARNING: this typically returns 3,000-4,500 tickers. Downloading full
    price history for all of them via yfinance can take a long time (each
    request is rate-limited) and Yahoo Finance may start throttling you.
    Use `limit=` on fetch_and_store()/fetch_universe() to test with a
    smaller slice first.

    Returns dict {symbol: (name, exchange, currency, sector)}. `sector` is
    left blank since this feed doesn't include it.
    """
    url = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    lines = resp.text.strip().split("\n")
    result = {}
    for line in lines[1:]:  # skip header row
        if not line or line.startswith("File Creation Time"):
            continue  # footer row present in the raw feed; not real data
        parts = line.split("|")
        if len(parts) < 7:
            continue
        symbol, name, market_category, test_issue, financial_status, round_lot, etf = parts[:7]
        if not include_test_issues and test_issue == "Y":
            continue
        if not include_etfs and etf == "Y":
            continue
        yf_symbol = symbol.replace(".", "-")  # yfinance convention, e.g. share classes
        result[yf_symbol] = (name, "NASDAQ", "USD", "")
    return result


def list_exchanges():
    """Returns {exchange_code: number_of_tickers} for all registered exchanges."""
    return {code: len(d) for code, d in EXCHANGE_REGISTRY.items()}


def get_exchange_tickers(exchange_code: str) -> dict:
    """
    Returns the curated ticker dict for one exchange, e.g. get_exchange_tickers("NASDAQ_HELSINKI").
    Raises ValueError with the valid options if the code isn't recognized.
    """
    code = exchange_code.upper()
    if code not in EXCHANGE_REGISTRY:
        available = ", ".join(sorted(EXCHANGE_REGISTRY.keys()))
        raise ValueError(f"Unknown exchange '{exchange_code}'. Available: {available}")
    return dict(EXCHANGE_REGISTRY[code])


def load_tickers_from_csv(path: str, default_market: str = "EU",
                           default_exchange: str = "", default_currency: str = "",
                           default_sector: str = "") -> dict:
    """
    Loads a ticker universe from a CSV file, for full/authoritative exchange
    listings that go beyond the curated dicts above (e.g. a full instrument
    list downloaded from Nasdaq Nordic, your broker, or another data vendor).

    Expected columns (case-insensitive; only 'symbol' is required):
      symbol, name, exchange, currency, sector

    Any missing optional column falls back to the default_* argument for
    every row. The symbol must already be in the exact format yfinance
    expects (e.g. "NOKIA.HE", "SAP.DE").

    Returns dict {symbol: (name, exchange, currency, sector)} suitable for
    passing straight to fetch_and_store(..., meta=result).
    """
    result = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # normalize header names to lowercase for lookup
        fieldmap = {name.lower().strip(): name for name in (reader.fieldnames or [])}
        if "symbol" not in fieldmap:
            raise ValueError("CSV must have a 'symbol' column")

        for row in reader:
            symbol = row[fieldmap["symbol"]].strip()
            if not symbol:
                continue
            name = row.get(fieldmap.get("name", ""), "").strip() if "name" in fieldmap else ""
            exchange = row.get(fieldmap.get("exchange", ""), "").strip() if "exchange" in fieldmap else ""
            currency = row.get(fieldmap.get("currency", ""), "").strip() if "currency" in fieldmap else ""
            sector = row.get(fieldmap.get("sector", ""), "").strip() if "sector" in fieldmap else ""
            result[symbol] = (
                name or symbol,
                exchange or default_exchange,
                currency or default_currency,
                sector or default_sector,
            )
    return result


def get_universe(market: str):
    """
    market: 'US', 'EU', 'ALL', or 'NASDAQ_FULL'
      'US'          -> current S&P 500 constituents (~500 tickers)
      'EU'          -> combined curated list across all EU exchanges (~275 tickers)
      'ALL'         -> 'US' + 'EU' combined
      'NASDAQ_FULL' -> every security natively listed on Nasdaq (~3,000-4,500
                       tickers, live-fetched, excludes ETFs/test issues by default)
    Returns dict {symbol: (name, exchange, currency, sector)}
    """
    market = market.upper()
    if market == "US":
        return fetch_sp500_tickers()
    elif market == "EU":
        return dict(EU_BLUE_CHIPS)
    elif market == "ALL":
        combined = fetch_sp500_tickers()
        combined.update(EU_BLUE_CHIPS)
        return combined
    elif market == "NASDAQ_FULL":
        return fetch_nasdaq_full_tickers()
    else:
        raise ValueError("market must be 'US', 'EU', 'ALL', or 'NASDAQ_FULL'")
