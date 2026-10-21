run_map = {
    ("Run2022C", "Run2022D"): "Run2022CD",
    ("Run2022E",): "Run2022E",
    ("Run2022F",): "Run2022F",
    ("Run2022G",): "Run2022G",
    ("Run2023Cv1", "Run2023Cv2", "Run2023Cv3"): "Run2023Cv123",
    ("Run2023Cv4",): "Run2023Cv4",
    ("Run2023D",): "Run2023D",
    ("Run2024C",): "Run2024C",
    ("Run2024D",): "Run2024D",
    ("Run2024E",): "Run2024E",
    ("Run2024F",): "Run2024F",
    ("Run2024G",): "Run2024G",
    ("Run2024H",): "Run2024H",
    ("Run2024I",): "Run2024I",
}

#https://cms-jme-jerc.docs.cern.ch/application/jec/#optional-l5-flavor-corrections

jec_eras_txt = {
    "2022_mc": "Summer22_22Sep2023_V4_MC",
    "2022EE_mc": "Summer22EE_22Sep2023_V4_MC",
    "2023_mc": "Summer23Prompt23_V4_MC",
    "2023BPix_mc": "Summer23BPixPrompt23_V4_MC",
    "2024_mc": "Summer24Prompt24_V5_MC",
    "2022_Run2022CD": "Summer2222Sep2023_RunCD_V4_DATA",
    "2022EE_Run2022E": "Summer22EE22Sep2023_RunE_V4_DATA",
    "2022EE_Run2022F": "Summer22EE22Sep2023_RunF_V4_DATA",
    "2022EE_Run2022G": "Summer22EE22Sep2023_RunG_V4_DATA",
    "2023_Run2023Cv123": "Summer23Prompt23_RunCv123_V4_DATA",
    "2023_Run2023Cv4": "Summer23Prompt23_RunCv4_V4_DATA",
    "2023BPix_Run2023D": "Summer23BPixPrompt23_RunD_V4_DATA",
    "2024_Run2024C": "Summer24Prompt24_RunCnib1_V5_DATA",
    "2024_Run2024D": "Summer24Prompt24_RunDnib1_V5_DATA",
    "2024_Run2024E": "Summer24Prompt24_RunEnib1_V5_DATA",
    "2024_Run2024F": "Summer24Prompt24_RunFnib1_V5_DATA",
    "2024_Run2024G": "Summer24Prompt24_RunGnib1_V5_DATA",
    "2024_Run2024H": "Summer24Prompt24_RunHnib1_V5_DATA",
    "2024_Run2024I": "Summer24Prompt24_RunInib1_V5_DATA",
}

jec_eras = {
    "2022": "Summer22_22Sep2023_V4",
    "2022EE": "Summer22EE_22Sep2023_V4",
    "2023": "Summer23Prompt23_V4",
    "2023BPix": "Summer23BPixPrompt23_V4",
    "2024": "Summer24Prompt24_V5",
}

jer_eras_txt = {
    "2022_mc": "Summer22_22Sep2023_JRV2_MC",
    "2022EE_mc": "Summer22EE_22Sep2023_JRV2_MC",
    "2023_mc": "Summer23Prompt23_RunCv1234_JRV3_MC",
    "2023BPix_mc": "Summer23BPixPrompt23_RunD_JRV3_MC",
    "2024_mc": "Summer24Prompt24_JRV2_MC",
}

jer_eras = {
    "2022": "Summer22_22Sep2023_JRV2",
    "2022EE": "Summer22EE_22Sep2023_JRV2",
    "2023": "Summer23Prompt23_RunCv1234_JRV3",
    "2023BPix": "Summer23BPixPrompt23_RunD_JRV3",
    "2024": "Summer24Prompt24_JRV2",
}

jerc_variations = {
    "JES": "JES_jes",
    "JER": "JER",
    "UES": "MET_UnclusteredEnergy",
}
