import json

from alive_progress import alive_it


def generate_queries(config):
    print("> Generating queries from templates...")

    with open(config.get_query_template_path()) as f:
        templates = json.load(f)

    queries = []

    for template in alive_it(templates):
        query = config.get_query_gen().generate_query(template)
        queries.append(
            {
                "name": template["name"],
                "description": template["description"],
                "primary_collection": template["primary_collection"],
                "query": query,
            }
        )

    print("> Queries generated successfully!")

    return queries


def main(config):
    config.display_config()
    print("> Starting query generation process...")
    print("-" * 50)

    queries = generate_queries(config)

    print("> Query generation completed successfully!")

    return queries
