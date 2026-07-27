import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

positions = {
    'Gene': (0, 0),
    'Disease': (3.5, 2.5),
    'Drug': (-3.5, 2.5),
    'Variant': (2, -2.5),
    'Pathway': (-2, -2.5),
    'BiologicalProcess': (-4.5, -1.5),
    'MolecularFunction': (-5, 0.5),
    'CellularComponent': (-4, -3.5),
    'BodyPart': (3.5, -1.5),
    'ClinicalTrial': (0, 4.5),
    'TranscriptionFactor': (1.5, -4.5),
    'Phenotype': (5, 0),
    'SideEffect': (-6, 3),
    'Symptom': (6, 3),
    'GeneFamily': (-1.5, -4.5),
    'PharmacologicClass': (-6, 1.5),
    'DrugLabel': (-5.5, 4.5),
}

colors = {
    'Gene': '#4C72B0',
    'Disease': '#DD5144',
    'Drug': '#55A868',
    'Variant': '#C4AD66',
    'Pathway': '#8172B2',
    'BiologicalProcess': '#937860',
    'MolecularFunction': '#DA8BC3',
    'CellularComponent': '#8C8C8C',
    'BodyPart': '#CCB974',
    'ClinicalTrial': '#64B5CD',
    'TranscriptionFactor': '#4C72B0',
    'Phenotype': '#E5AE38',
    'SideEffect': '#B07AA1',
    'Symptom': '#FF9DA7',
    'GeneFamily': '#76B7B2',
    'PharmacologicClass': '#9D7660',
    'DrugLabel': '#BAB0AC',
}

node_counts = {
    'Gene': 193795,
    'Disease': 12012,
    'Drug': 26794,
    'Variant': 4488042,
    'Pathway': 2532,
    'BiologicalProcess': 29688,
    'MolecularFunction': 11169,
    'CellularComponent': 4176,
    'BodyPart': 14937,
    'ClinicalTrial': 21578,
    'TranscriptionFactor': 1120,
    'Phenotype': 19389,
    'SideEffect': 5734,
    'Symptom': 966,
    'GeneFamily': 1934,
    'PharmacologicClass': 559,
    'DrugLabel': 345,
}

edges_data = [
    ('Gene', 'geneAssociatesWithDisease', 'Disease'),
    ('Gene', 'geneInPathway', 'Pathway'),
    ('Gene', 'geneParticipatesInBP', 'BiologicalProcess'),
    ('Gene', 'geneHasMolecularFunction', 'MolecularFunction'),
    ('Gene', 'geneAssocWithCC', 'CellularComponent'),
    ('Gene', 'geneInteractsWithGene', 'Gene'),
    ('Gene', 'geneRegulatesGene', 'Gene'),
    ('Gene', 'geneExpressedInBodyPart', 'BodyPart'),
    ('Gene', 'geneInFamily', 'GeneFamily'),
    ('Gene', 'geneAssocWithPhenotype', 'Phenotype'),
    ('Gene', 'hasVariant', 'Variant'),
    ('Gene', 'AFFECTS_RESPONSE_TO', 'Drug'),
    ('Gene', 'AFFECTS_RESPONSE_TO_CLASS', 'PharmacologicClass'),
    ('Drug', 'drugBindsGene', 'Gene'),
    ('Drug', 'chemicalBindsGene', 'Gene'),
    ('Drug', 'chemIncreasesExpr', 'Gene'),
    ('Drug', 'chemDecreasesExpr', 'Gene'),
    ('Drug', 'compoundUpregGene', 'Gene'),
    ('Drug', 'compoundDownregGene', 'Gene'),
    ('Drug', 'drugTreatsDisease', 'Disease'),
    ('Drug', 'drugPalliatesDisease', 'Disease'),
    ('Drug', 'compoundCausesSE', 'SideEffect'),
    ('Drug', 'predictedTreatsDisease', 'Disease'),
    ('Drug', 'drugTreatsPhenotype', 'Phenotype'),
    ('Disease', 'diseaseIsSubtypeOf', 'Disease'),
    ('Disease', 'diseaseLocalizesToAnatomy', 'BodyPart'),
    ('Disease', 'diseasePresentsSymptom', 'Symptom'),
    ('Disease', 'diseaseAssocWithDisease', 'Disease'),
    ('ClinicalTrial', 'STUDIES_CONDITION', 'Disease'),
    ('ClinicalTrial', 'TESTS_INTERVENTION', 'Drug'),
    ('TranscriptionFactor', 'tfInteractsWithGene', 'Gene'),
    ('Variant', 'VARIANT_IN', 'Gene'),
    ('DrugLabel', 'dlAnnotatesGene', 'Gene'),
    ('DrugLabel', 'dlDescribesDrug', 'Drug'),
    ('PharmacologicClass', 'pharmClassIncludesDrug', 'Drug'),
    ('BodyPart', 'bpExpressesGene', 'Gene'),
]

fig, ax = plt.subplots(1, 1, figsize=(20, 16))
ax.set_xlim(-8, 8)
ax.set_ylim(-6.5, 6.5)
ax.set_aspect('equal')
ax.axis('off')
fig.patch.set_facecolor('white')

drawn_pairs = {}
for src, rel, tgt in edges_data:
    sx, sy = positions[src]
    tx, ty = positions[tgt]

    pair_key = (min(src, tgt), max(src, tgt))
    if pair_key not in drawn_pairs:
        drawn_pairs[pair_key] = 0
    drawn_pairs[pair_key] += 1
    count = drawn_pairs[pair_key]

    if src == tgt:
        continue

    offsets = {1: 0, 2: 0.15, 3: -0.15, 4: 0.28, 5: -0.28, 6: 0.4, 7: -0.4, 8: 0.5}
    curve = offsets.get(count, 0.1 * count)

    if 'Treats' in rel or 'treats' in rel or 'Palliates' in rel:
        ecolor = '#2ca02c'
    elif 'predicted' in rel:
        ecolor = '#ff7f0e'
    elif 'Binds' in rel or 'binds' in rel or 'Interacts' in rel or 'interacts' in rel:
        ecolor = '#1f77b4'
    elif ('Regulates' in rel or 'regulates' in rel or 'Increases' in rel or
          'Decreases' in rel or 'Upreg' in rel or 'Downreg' in rel or
          'Expr' in rel or 'Express' in rel):
        ecolor = '#9467bd'
    elif 'Associates' in rel or 'Assoc' in rel or 'Resembles' in rel:
        ecolor = '#d62728'
    else:
        ecolor = '#7f7f7f'

    style = '--' if 'predicted' in rel else '-'
    lw = 2.0 if ('predicted' in rel or 'Treats' in rel or 'treats' in rel) else 1.2

    ax.annotate('',
        xy=(tx, ty), xytext=(sx, sy),
        arrowprops=dict(
            arrowstyle='->',
            color=ecolor,
            lw=lw,
            alpha=0.45,
            connectionstyle='arc3,rad={}'.format(curve),
            linestyle=style,
            mutation_scale=15,
        ))

for node_type, (x, y) in positions.items():
    r = max(0.55, min(1.0, np.log10(node_counts.get(node_type, 1000)) / 6.5 * 0.9))

    circle = plt.Circle((x, y), r,
                         color=colors[node_type],
                         ec='white',
                         linewidth=2.5,
                         zorder=10,
                         alpha=0.9)
    ax.add_patch(circle)

    label = node_type
    fontsize = 9
    splits = {
        'BiologicalProcess': ('Biological\nProcess', 8),
        'MolecularFunction': ('Molecular\nFunction', 8),
        'CellularComponent': ('Cellular\nComponent', 8),
        'TranscriptionFactor': ('Transcription\nFactor', 7.5),
        'PharmacologicClass': ('Pharmacologic\nClass', 7.5),
        'ClinicalTrial': ('Clinical\nTrial', 8.5),
        'GeneFamily': ('Gene\nFamily', 8.5),
        'DrugLabel': ('Drug\nLabel', 8.5),
        'SideEffect': ('Side\nEffect', 8.5),
        'BodyPart': ('Body\nPart', 8.5),
    }
    if node_type in splits:
        label, fontsize = splits[node_type]

    ax.text(x, y, label, ha='center', va='center', fontsize=fontsize,
            fontweight='bold', color='white', zorder=11, linespacing=0.9)

    count_str = '{:,}'.format(node_counts.get(node_type, 0))
    ax.text(x, y - r - 0.18, count_str, ha='center', va='top', fontsize=6.5,
            color='#555555', zorder=11)

ax.text(0, 6.1, 'CardioKB Schema', ha='center', va='center', fontsize=16, fontweight='bold')
ax.text(0, 5.65,
        '17 Node Types  |  28 Relationship Types  |  23 Data Sources\n'
        '453,037 Nodes  |  5,461,783 Relationships',
        ha='center', va='center', fontsize=10, color='#555555')

edge_categories = [
    ('Treatment / Palliation', '#2ca02c', '-'),
    ('ML Prediction', '#ff7f0e', '--'),
    ('Binding / Interaction', '#1f77b4', '-'),
    ('Regulation / Expression', '#9467bd', '-'),
    ('Association', '#d62728', '-'),
    ('Other (ontology, clinical)', '#7f7f7f', '-'),
]

lx = 6.0
ly = -3.8
ax.text(lx + 0.5, ly + 0.5, 'Edge Categories', ha='center', fontsize=9, fontweight='bold')
for i, (label, color, ls) in enumerate(edge_categories):
    y = ly - i * 0.4
    ax.plot([lx - 0.3, lx + 0.4], [y, y], color=color, lw=2.5, linestyle=ls)
    ax.text(lx + 0.6, y, label, va='center', fontsize=7.5)

plt.tight_layout()
out = '/Users/nawaza/Desktop/Cardio-KB/docs/cardiokb_schema'
fig.savefig(out + '.png', dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
fig.savefig(out + '.pdf', bbox_inches='tight', facecolor='white', edgecolor='none')
print('Saved:', out + '.png', out + '.pdf')
