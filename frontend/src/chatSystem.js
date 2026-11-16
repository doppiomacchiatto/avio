// System prompt for the AI Chat tab. It tells the model the truth about what it has: no org
// selected, the org's object list still loading, loaded, or empty. Chat works in every state;
// the object list only adds object-aware answers once it is there.

const HEAD = "You are a Salesforce expert assistant embedded in Avio, a Salesforce metadata tool.";

export function buildChatSystem(org, ctx) {
  const objects = ctx?.objects || [];

  if (!org) {
    return [
      HEAD,
      "No Salesforce org is selected right now. Answer general Salesforce questions normally.",
      "Only if the user asks about objects, fields or data in their own org, tell them to click Select Org first.",
    ].join("\n");
  }

  const lines = [HEAD, `The user is connected to the Salesforce org "${org.alias}".`];

  if (objects.length === 0) {
    if (ctx?.objectsLoaded) {
      lines.push("Loading finished but this org returned no objects. Answer general Salesforce questions normally.");
    } else {
      lines.push(
        "The list of this org's objects is still loading in the background, so you do not have it yet. " +
        "Answer general Salesforce questions and greetings normally; do NOT say that no org is connected.",
        "If the user asks about a specific object in their org, say the object list is still loading and ask them to try again in a few seconds."
      );
    }
    return lines.join("\n");
  }

  const objList = objects.map((o, i) => `${i + 1}. ${o.apiName} — ${o.label}`).join("\n");
  lines.push(
    "When the user asks about a Salesforce object, match it against this exact list and use the API name precisely:",
    "",
    objList,
    "",
    "When you identify an object to query, output a tag: [SELECT_OBJECT: ApiName__c]",
    "Always use the exact API names from the list above."
  );
  return lines.join("\n");
}
