from sentence_transformers import SentenceTransformer, util
from sklearn.metrics.pairwise import cosine_similarity



def text_similarity_score(text1,text2,model):
    """
    Compute a semantic similarity score between two texts using cosine similarity.
    :param text1: The first text string
    :param text2: The second text string
    :param model: A loaded SentenceTransformer model
    :return: A float simialrity score between 0 and 1
    """
    
    #Get the embeddings for both texts
    embeddings = model.encode([text1, text2])
    
    # Compute cosine similariyt between the two embeddings
    score = cosine_similarity([embeddings[0]],[embeddings[1]])[0][0]
    
    return score 


model = SentenceTransformer('all-MiniLM-L6-v2')

text1 = "2008polovivo1.6"
text2 = "2008polovivo1.6gle"


score = text_similarity_score(text1,text2,model)

print("Text Similarity Score: ",score)