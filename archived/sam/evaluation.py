"""
SAM Evaluation Framework

Compares SAM spreading activation retrieval against simple vector baseline.
Uses LLM-as-judge to evaluate result quality against ground truth.

Metrics:
- Precision: What fraction of retrieved facts are relevant?
- Recall: What fraction of ground truth facts were retrieved?
- LLM Score: How well does the retrieved context answer the query?
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv


@dataclass
class EvaluationResult:
    """Result for a single test case."""
    test_id: str
    category: str
    query: str
    
    # SAM results
    sam_retrieved: List[str]
    sam_precision: float
    sam_recall: float
    sam_llm_score: float
    
    # Vector baseline results
    vector_retrieved: List[str]
    vector_precision: float
    vector_recall: float
    vector_llm_score: float
    
    # Comparison
    sam_wins: bool
    llm_explanation: str
    
    # Ground truth
    ground_truth: List[str]


@dataclass
class EvaluationSummary:
    """Summary statistics across all test cases."""
    total_cases: int
    sam_wins: int
    vector_wins: int
    ties: int
    
    avg_sam_precision: float
    avg_sam_recall: float
    avg_sam_llm_score: float
    
    avg_vector_precision: float
    avg_vector_recall: float
    avg_vector_llm_score: float
    
    results: List[EvaluationResult] = field(default_factory=list)


class RetrievalEvaluator:
    """
    Evaluates retrieval quality using multiple metrics.
    """
    
    def __init__(self, llm_client):
        """Initialize with LLM client for judging."""
        self.llm_client = llm_client
    
    def compute_precision_recall(
        self,
        retrieved_facts: List[str],
        ground_truth: List[str],
        similarity_threshold: float = 0.5
    ) -> Tuple[float, float]:
        """
        Compute precision and recall using fuzzy string matching.
        
        Precision = relevant_retrieved / total_retrieved
        Recall = relevant_retrieved / total_ground_truth
        """
        if not retrieved_facts:
            return 0.0, 0.0
        
        # Count how many retrieved facts match ground truth
        relevant_retrieved = 0
        matched_ground_truth = set()
        
        for retrieved in retrieved_facts:
            retrieved_lower = retrieved.lower()
            
            for i, gt in enumerate(ground_truth):
                if i in matched_ground_truth:
                    continue
                
                gt_lower = gt.lower()
                
                # Check if ground truth keywords appear in retrieved
                gt_words = set(gt_lower.split())
                retrieved_words = set(retrieved_lower.split())
                
                # Calculate word overlap
                overlap = len(gt_words & retrieved_words)
                max_possible = min(len(gt_words), len(retrieved_words))
                
                if max_possible > 0 and overlap / max_possible >= similarity_threshold:
                    relevant_retrieved += 1
                    matched_ground_truth.add(i)
                    break
        
        precision = relevant_retrieved / len(retrieved_facts) if retrieved_facts else 0.0
        recall = len(matched_ground_truth) / len(ground_truth) if ground_truth else 0.0
        
        return precision, recall
    
    async def llm_judge(
        self,
        query: str,
        retrieved_context: str,
        ground_truth: List[str],
        method_name: str
    ) -> Tuple[float, str]:
        """
        Use LLM to judge retrieval quality.
        
        Returns:
            score (0-10): How well the retrieved context answers the query
            explanation: Why the LLM gave this score
        """
        prompt = f"""You are evaluating a memory retrieval system. 

QUERY: {query}

GROUND TRUTH FACTS (what should ideally be retrieved):
{chr(10).join(f"- {fact}" for fact in ground_truth)}

RETRIEVED CONTEXT ({method_name}):
{retrieved_context if retrieved_context else "(No results retrieved)"}

TASK: Score the retrieved context from 0-10 based on:
1. Coverage: Does it contain the ground truth facts? (0-4 points)
2. Relevance: Are the retrieved facts relevant to the query? (0-3 points)
3. Precision: Is there minimal irrelevant noise? (0-3 points)

Respond in JSON format:
{{"score": <0-10>, "explanation": "<brief explanation>"}}
"""
        
        try:
            response = self.llm_client.complete_json(prompt)
            return response.get("score", 5), response.get("explanation", "")
        except Exception as e:
            print(f"  ⚠ LLM judge failed: {e}")
            return 5.0, f"Error: {str(e)}"
    
    async def compare_methods(
        self,
        query: str,
        sam_context: str,
        vector_context: str,
        ground_truth: List[str]
    ) -> Tuple[str, str]:
        """
        Use LLM to compare SAM vs Vector and pick a winner.
        
        Returns:
            winner: "sam", "vector", or "tie"
            explanation: Why
        """
        prompt = f"""You are comparing two memory retrieval methods for a query.

QUERY: {query}

GROUND TRUTH FACTS (what should ideally be retrieved):
{chr(10).join(f"- {fact}" for fact in ground_truth)}

METHOD A (Spreading Activation Memory - SAM):
{sam_context if sam_context else "(No results)"}

METHOD B (Simple Vector Search):
{vector_context if vector_context else "(No results)"}

Which method retrieved more relevant and useful information for answering the query?

Consider:
1. Which method captured more ground truth facts?
2. Which method had less irrelevant noise?
3. Which method would be more helpful for an AI assistant?

Respond in JSON format:
{{"winner": "A" or "B" or "tie", "explanation": "<brief explanation>"}}
"""
        
        try:
            response = self.llm_client.complete_json(prompt)
            winner_map = {"A": "sam", "B": "vector", "tie": "tie"}
            winner = winner_map.get(response.get("winner", "tie"), "tie")
            return winner, response.get("explanation", "")
        except Exception as e:
            print(f"  ⚠ Comparison failed: {e}")
            return "tie", f"Error: {str(e)}"


async def run_evaluation(
    store,
    sam_retriever,
    vector_retriever,
    llm_client,
    evaluation_data: Dict,
    tenant_id: str,
    use_enhanced_retrieval: bool = True
) -> EvaluationSummary:
    """
    Run full evaluation comparing SAM vs Vector retrieval.
    
    Args:
        use_enhanced_retrieval: If True, use retrieve_with_analysis for
            improved multi-hop handling with auto-tuned parameters.
    """
    evaluator = RetrievalEvaluator(llm_client)
    results = []
    case_analysis = []  # Detailed analysis for each case
    
    test_cases = evaluation_data.get("test_cases", [])
    print(f"\n{'='*70}")
    print(f"Running Evaluation: {len(test_cases)} test cases")
    print(f"{'='*70}")
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] {case['category']}: {case['query'][:50]}...")
        
        query = case["query"]
        goal = case.get("goal")
        ground_truth = case["ground_truth_facts"]
        is_multi_hop = case["category"].startswith("multi_hop")
        
        # Run SAM retrieval with enhanced analysis for multi-hop
        query_plan = None
        if use_enhanced_retrieval:
            sam_result, query_plan = await sam_retriever.retrieve_with_analysis(
                query=query,
                tenant_id=tenant_id,
                goal=goal,
                max_results=10,
                auto_tune=True
            )
            if query_plan:
                print(f"  📊 Entities: {query_plan.extracted_entities[:3]}...")
                print(f"  🔗 Multi-hop: {query_plan.requires_multi_hop} ({query_plan.estimated_hops} hops)")
        else:
            sam_result = await sam_retriever.retrieve(
                query=query,
                tenant_id=tenant_id,
                goal=goal,
                max_results=10
            )
        sam_context = await sam_retriever._format_context(sam_result, tenant_id, 2000)
        sam_facts = [n.node_id for n in sam_result.activated_nodes]
        
        # Get actual claim content for SAM results
        # For Entity nodes, fetch their associated claims to get actual facts
        sam_contents = []
        seen_claims = set()  # Avoid duplicates by ID
        seen_content = set()  # Avoid duplicates by content
        for node in sam_result.activated_nodes:
            full_node = await store.get_node(node.node_id, tenant_id)
            if full_node and hasattr(full_node, 'content'):
                # Claim or other content-bearing node
                content = full_node.content
                if content not in seen_content:
                    sam_contents.append(content)
                    seen_content.add(content)
            elif full_node and hasattr(full_node, 'name'):
                # Entity node - fetch associated claims to get actual facts
                entity_claims = []
                try:
                    entity_claims = await store.get_claims_for_entity(node.node_id, tenant_id)
                except Exception as e:
                    print(f"      [Debug] Error fetching claims for {full_node.name}: {e}")
                
                if entity_claims:
                    for claim in entity_claims[:5]:  # Top 5 claims per entity
                        claim_id = getattr(claim, 'id', None) or getattr(claim, 'claim_id', None) or claim.content[:50]
                        content = claim.content
                        # Deduplicate by both ID and content
                        if claim_id not in seen_claims and content not in seen_content:
                            sam_contents.append(content)
                            seen_claims.add(claim_id)
                            seen_content.add(content)
                else:
                    # No claims found - include entity name as fallback
                    if full_node.name not in seen_content:
                        sam_contents.append(full_node.name)
                        seen_content.add(full_node.name)
        
        # Run Vector baseline
        vector_result = await vector_retriever.retrieve(
            query=query,
            tenant_id=tenant_id,
            max_results=10
        )
        vector_context = await vector_retriever.retrieve_and_format(query, tenant_id, 10)
        vector_contents = [r.content for r in vector_result]
        
        # Compute metrics
        sam_precision, sam_recall = evaluator.compute_precision_recall(
            sam_contents, ground_truth
        )
        vector_precision, vector_recall = evaluator.compute_precision_recall(
            vector_contents, ground_truth
        )
        
        # LLM scoring
        sam_score, sam_exp = await evaluator.llm_judge(
            query, sam_context, ground_truth, "SAM"
        )
        vector_score, vector_exp = await evaluator.llm_judge(
            query, vector_context, ground_truth, "Vector"
        )
        
        # Compare methods
        winner, comparison_exp = await evaluator.compare_methods(
            query, sam_context, vector_context, ground_truth
        )
        
        result = EvaluationResult(
            test_id=case["id"],
            category=case["category"],
            query=query,
            sam_retrieved=sam_contents[:5],  # Top 5 for readability
            sam_precision=sam_precision,
            sam_recall=sam_recall,
            sam_llm_score=sam_score,
            vector_retrieved=vector_contents[:5],
            vector_precision=vector_precision,
            vector_recall=vector_recall,
            vector_llm_score=vector_score,
            sam_wins=(winner == "sam"),
            llm_explanation=comparison_exp,
            ground_truth=ground_truth
        )
        results.append(result)
        
        # Print progress
        print(f"  SAM:    P={sam_precision:.2f} R={sam_recall:.2f} LLM={sam_score:.1f}")
        print(f"  Vector: P={vector_precision:.2f} R={vector_recall:.2f} LLM={vector_score:.1f}")
        print(f"  Winner: {winner.upper()}")
        
        # Store detailed analysis
        case_analysis.append({
            "test_id": case["id"],
            "category": case["category"],
            "query": query,
            "is_multi_hop": is_multi_hop,
            "query_plan": {
                "entities": query_plan.extracted_entities if query_plan else [],
                "search_terms": query_plan.search_terms if query_plan else [],
                "requires_multi_hop": query_plan.requires_multi_hop if query_plan else False,
                "estimated_hops": query_plan.estimated_hops if query_plan else 1,
            } if query_plan else None,
            "sam_retrieved_preview": sam_contents[:3],
            "vector_retrieved_preview": vector_contents[:3],
            "ground_truth": ground_truth,
            "sam_precision": sam_precision,
            "sam_recall": sam_recall,
            "sam_llm_score": sam_score,
            "vector_precision": vector_precision,
            "vector_recall": vector_recall,
            "vector_llm_score": vector_score,
            "winner": winner,
            "explanation": comparison_exp
        })
    
    # Compute summary
    sam_wins = sum(1 for r in results if r.sam_wins)
    vector_wins = sum(1 for r in results if r.vector_llm_score > r.sam_llm_score)
    ties = len(results) - sam_wins - vector_wins
    
    summary = EvaluationSummary(
        total_cases=len(results),
        sam_wins=sam_wins,
        vector_wins=vector_wins,
        ties=ties,
        avg_sam_precision=sum(r.sam_precision for r in results) / len(results),
        avg_sam_recall=sum(r.sam_recall for r in results) / len(results),
        avg_sam_llm_score=sum(r.sam_llm_score for r in results) / len(results),
        avg_vector_precision=sum(r.vector_precision for r in results) / len(results),
        avg_vector_recall=sum(r.vector_recall for r in results) / len(results),
        avg_vector_llm_score=sum(r.vector_llm_score for r in results) / len(results),
        results=results
    )
    
    # Print multi-hop specific analysis
    multi_hop_results = [a for a in case_analysis if a["is_multi_hop"]]
    if multi_hop_results:
        print(f"\n{'─'*70}")
        print("MULTI-HOP QUERY ANALYSIS")
        print(f"{'─'*70}")
        mh_sam_wins = sum(1 for a in multi_hop_results if a["winner"] == "sam")
        mh_vec_wins = sum(1 for a in multi_hop_results if a["winner"] == "vector")
        mh_ties = len(multi_hop_results) - mh_sam_wins - mh_vec_wins
        print(f"Multi-hop cases: {len(multi_hop_results)}")
        print(f"  SAM wins: {mh_sam_wins} ({100*mh_sam_wins/len(multi_hop_results):.0f}%)")
        print(f"  Vector wins: {mh_vec_wins} ({100*mh_vec_wins/len(multi_hop_results):.0f}%)")
        print(f"  Ties: {mh_ties} ({100*mh_ties/len(multi_hop_results):.0f}%)")
        
        for case in multi_hop_results:
            print(f"\n  [{case['test_id']}] {case['category']}")
            print(f"    Query: {case['query'][:60]}...")
            if case['query_plan']:
                print(f"    Entities detected: {case['query_plan']['entities'][:3]}")
                print(f"    Estimated hops: {case['query_plan']['estimated_hops']}")
            print(f"    SAM: P={case['sam_precision']:.2f} R={case['sam_recall']:.2f} LLM={case['sam_llm_score']:.1f}")
            print(f"    Vec: P={case['vector_precision']:.2f} R={case['vector_recall']:.2f} LLM={case['vector_llm_score']:.1f}")
            print(f"    Winner: {case['winner'].upper()}")
            print(f"    Reason: {case['explanation'][:100]}...")
    
    return summary


def print_evaluation_report(summary: EvaluationSummary):
    """Print a formatted evaluation report."""
    print(f"\n{'='*70}")
    print("EVALUATION REPORT")
    print(f"{'='*70}")
    
    print(f"\n📊 Overall Results ({summary.total_cases} test cases)")
    print(f"   SAM Wins:    {summary.sam_wins} ({100*summary.sam_wins/summary.total_cases:.0f}%)")
    print(f"   Vector Wins: {summary.vector_wins} ({100*summary.vector_wins/summary.total_cases:.0f}%)")
    print(f"   Ties:        {summary.ties} ({100*summary.ties/summary.total_cases:.0f}%)")
    
    print(f"\n📈 Average Metrics")
    print(f"   {'Metric':<15} {'SAM':>10} {'Vector':>10} {'Δ':>10}")
    print(f"   {'-'*45}")
    print(f"   {'Precision':<15} {summary.avg_sam_precision:>10.2f} {summary.avg_vector_precision:>10.2f} {summary.avg_sam_precision - summary.avg_vector_precision:>+10.2f}")
    print(f"   {'Recall':<15} {summary.avg_sam_recall:>10.2f} {summary.avg_vector_recall:>10.2f} {summary.avg_sam_recall - summary.avg_vector_recall:>+10.2f}")
    print(f"   {'LLM Score':<15} {summary.avg_sam_llm_score:>10.1f} {summary.avg_vector_llm_score:>10.1f} {summary.avg_sam_llm_score - summary.avg_vector_llm_score:>+10.1f}")
    
    print(f"\n📋 Per-Category Results")
    categories = {}
    for r in summary.results:
        if r.category not in categories:
            categories[r.category] = {"sam_wins": 0, "total": 0}
        categories[r.category]["total"] += 1
        if r.sam_wins:
            categories[r.category]["sam_wins"] += 1
    
    for cat, stats in sorted(categories.items()):
        pct = 100 * stats["sam_wins"] / stats["total"]
        print(f"   {cat:<20} SAM: {stats['sam_wins']}/{stats['total']} ({pct:.0f}%)")
    
    print(f"\n📝 Detailed Results")
    for r in summary.results:
        winner = "SAM ✓" if r.sam_wins else "Vector ✓" if r.vector_llm_score > r.sam_llm_score else "Tie"
        print(f"   [{r.test_id}] {r.category}: {winner}")
        print(f"      Query: {r.query[:60]}...")
        print(f"      SAM: P={r.sam_precision:.2f} R={r.sam_recall:.2f} LLM={r.sam_llm_score:.1f}")
        print(f"      Vec: P={r.vector_precision:.2f} R={r.vector_recall:.2f} LLM={r.vector_llm_score:.1f}")


def save_evaluation_results(summary: EvaluationSummary, output_path: str):
    """Save evaluation results to JSON."""
    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "summary": {
            "total_cases": summary.total_cases,
            "sam_wins": summary.sam_wins,
            "vector_wins": summary.vector_wins,
            "ties": summary.ties,
            "avg_sam_precision": summary.avg_sam_precision,
            "avg_sam_recall": summary.avg_sam_recall,
            "avg_sam_llm_score": summary.avg_sam_llm_score,
            "avg_vector_precision": summary.avg_vector_precision,
            "avg_vector_recall": summary.avg_vector_recall,
            "avg_vector_llm_score": summary.avg_vector_llm_score,
        },
        "results": [
            {
                "test_id": r.test_id,
                "category": r.category,
                "query": r.query,
                "ground_truth": r.ground_truth,
                "sam": {
                    "retrieved": r.sam_retrieved,
                    "precision": r.sam_precision,
                    "recall": r.sam_recall,
                    "llm_score": r.sam_llm_score,
                },
                "vector": {
                    "retrieved": r.vector_retrieved,
                    "precision": r.vector_precision,
                    "recall": r.vector_recall,
                    "llm_score": r.vector_llm_score,
                },
                "sam_wins": r.sam_wins,
                "explanation": r.llm_explanation,
            }
            for r in summary.results
        ]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✓ Results saved to {output_path}")
