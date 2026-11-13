from datasets import load_dataset

dataset = load_dataset("google/code_x_glue_cc_defect_detection")
dataset.save_to_disk("../data/codexglue_defect")